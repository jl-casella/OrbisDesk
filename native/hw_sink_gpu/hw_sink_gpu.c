/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W142 (phase 6): the presentation sink's output through the GPU.
 *
 * platform/ps4/pw_wine_sink_ps4.c copies every desktop frame into a VideoOut buffer on the
 * CPU (scale, opaque alpha, pointer). Here RADV (linked in the hardware ELF) does it:
 * - the two 1280x720 VideoOut buffers are linear Vulkan images in device-local host-visible
 *   memory at 2 MiB aligned addresses, registered with sceVideoOutRegisterBuffers as the G001
 *   probe did (native/vk_probe/main.c);
 * - each frame is one full-screen triangle (shaders in this folder) into the buffer to show;
 *   the sink waits for its fence and flips.
 * W144 (step 2): the GPU also stacks the windows. Their contents, the wallpaper and the
 * desktop win32u falls back to live in one host-cached pool buffer (the CPU address is the GPU
 * address on the PS4, so the GPU reads them where GDI's copies land, with no upload). A frame
 * is a list of layers, bottom first, in a uniform buffer; the shader takes the top one under
 * each desktop pixel. The plain desktop of W142 is a frame of one layer.
 * W152: a layer may also be an image outside the pool, read by its GPU address (a Vulkan
 * program's presented image, where Mesa's headless WSI leaves it): the device enables buffer
 * device addresses, and such layers are taken only when the pool's GPU address is its CPU
 * address, which is what lets a CPU pointer stand for a GPU address.
 * W153: and only when the compiled shader reads them without FLAT instructions (W152: the first
 * frame hung the GPU); else the shader without image layers (screen_frag_pool.h) draws.
 * Every failure is logged with the Vulkan result and leaves the sink on its CPU copy. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <orbis/VideoOut.h>
/* the entry points below are this file's own pointers, loaded from RADV */
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan_core.h>

#include "screen_frag.h"
#include "screen_frag_pool.h"
#include "screen_vert.h"

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance instance, const char *name);
extern PFN_vkVoidFunction vk_common_GetDeviceProcAddr(VkDevice device, const char *name);

/* the layout of struct pw_wine_layer in platform/ps4/pw_wine_sink_ps4.c */
struct layer {const uint32_t *pixels;int left,top,right,bottom;unsigned stride,flags,source_width,source_height;};
enum {LAYER_EXTERNAL=1,LAYER_RGBA=2};   /* as in screen.frag */

enum {FORMAT_A8R8G8B8_SRGB=(int)0x80000000,TILING_LINEAR=1,BUFFERS=2,MAX_LAYERS=65};
/* pool: 96 MiB, about 26 desktops of 1280x720; blocks start at 256 byte boundaries */
enum {POOL_BYTES=96<<20,POOL_ALIGN=256,POOL_BLOCKS=512};
static const VkFormat out_format=VK_FORMAT_R8G8B8A8_UNORM;
static VkPhysicalDevice gpu;
static VkDevice device;
static VkQueue queue;
static uint32_t family;
static VkPhysicalDeviceMemoryProperties memory;
static uint32_t max_texels;
static uint8_t *pool;
static size_t pool_bytes;
static struct {size_t at,bytes;} blocks[POOL_BLOCKS];   /* in use, by address */
static unsigned block_count;
static VkBufferView pool_view;
static VkBuffer layer_buffer;
/* left,top,right,bottom, offset,stride,flags,0, address low,high, source width,height */
static int32_t (*layer_data)[12];
static uint64_t pool_address;                      /* the pool's GPU address */
static int images;                                 /* layers outside the pool are taken (W152) */
static void *screen;
static unsigned screen_width,screen_height;
static unsigned out_width,out_height;
static VkFramebuffer framebuffers[BUFFERS];
static VkRenderPass pass;
static VkPipelineLayout layout;
static VkPipeline pipeline;
static VkDescriptorSet set;
static VkCommandBuffer cmd;
static VkFence fence;

#define DEVICE_FUNCTIONS(X) X(vkGetDeviceQueue) X(vkCreateBuffer) X(vkGetBufferMemoryRequirements) \
    X(vkAllocateMemory) X(vkBindBufferMemory) X(vkMapMemory) X(vkCreateBufferView) X(vkCreateImage) \
    X(vkGetImageMemoryRequirements) X(vkBindImageMemory) X(vkGetImageSubresourceLayout) X(vkCreateImageView) \
    X(vkCreateRenderPass) X(vkCreateFramebuffer) X(vkCreateShaderModule) X(vkCreateDescriptorSetLayout) \
    X(vkCreateDescriptorPool) X(vkAllocateDescriptorSets) X(vkUpdateDescriptorSets) X(vkCreatePipelineLayout) \
    X(vkCreateGraphicsPipelines) X(vkCreateCommandPool) X(vkAllocateCommandBuffers) X(vkBeginCommandBuffer) \
    X(vkEndCommandBuffer) X(vkResetCommandBuffer) X(vkCmdBeginRenderPass) X(vkCmdEndRenderPass) \
    X(vkCmdBindPipeline) X(vkCmdBindDescriptorSets) X(vkCmdPushConstants) X(vkCmdSetViewport) \
    X(vkCmdSetScissor) X(vkCmdDraw) X(vkCreateFence) X(vkResetFences) X(vkWaitForFences) X(vkQueueSubmit) \
    X(vkGetBufferDeviceAddressKHR) X(vkGetPipelineExecutablePropertiesKHR) \
    X(vkGetPipelineExecutableInternalRepresentationsKHR)
#define DECLARE(name) static PFN_##name name;
DEVICE_FUNCTIONS(DECLARE)
#undef DECLARE

#define TRY(call) do { VkResult r_=(call); \
    if(r_!=VK_SUCCESS) {fprintf(stderr,"PWSINK gpu_failed %s = %d\n",#call,(int)r_);return -1;} } while(0)

static int device_init(void)
{
    static int state;   /* 0 not tried, 1 ready, -1 failed */
    if(state) return state>0?0:-1;
    state=-1;
    PFN_vkCreateInstance create_instance=(PFN_vkCreateInstance)vk_icdGetInstanceProcAddr(NULL,"vkCreateInstance");
    if(!create_instance) {fprintf(stderr,"PWSINK gpu_failed no vkCreateInstance\n");return -1;}
    VkApplicationInfo app={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.pApplicationName="OrbisDesk sink",
                           .apiVersion=VK_API_VERSION_1_1};
    VkInstanceCreateInfo instance_info={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app};
    VkInstance instance;
    TRY(create_instance(&instance_info,NULL,&instance));
#define LOAD(name) PFN_##name name=(PFN_##name)vk_icdGetInstanceProcAddr(instance,#name); \
    if(!name) {fprintf(stderr,"PWSINK gpu_failed no %s\n",#name);return -1;}
    LOAD(vkEnumeratePhysicalDevices) LOAD(vkGetPhysicalDeviceMemoryProperties) LOAD(vkGetPhysicalDeviceProperties)
    LOAD(vkGetPhysicalDeviceQueueFamilyProperties) LOAD(vkCreateDevice) LOAD(vkGetPhysicalDeviceFeatures2)
#undef LOAD
    uint32_t count=1;
    VkResult r=vkEnumeratePhysicalDevices(instance,&count,&gpu);
    if((r!=VK_SUCCESS && r!=VK_INCOMPLETE) || !count) {fprintf(stderr,"PWSINK gpu_failed no physical device %d\n",(int)r);return -1;}
    vkGetPhysicalDeviceMemoryProperties(gpu,&memory);
    VkPhysicalDeviceProperties properties;vkGetPhysicalDeviceProperties(gpu,&properties);
    max_texels=properties.limits.maxTexelBufferElements;
    VkQueueFamilyProperties families[8];count=8;
    vkGetPhysicalDeviceQueueFamilyProperties(gpu,&count,families);
    for(family=0;family<count && !(families[family].queueFlags&VK_QUEUE_GRAPHICS_BIT);++family) {}
    if(family==count) {fprintf(stderr,"PWSINK gpu_failed no graphics queue\n");return -1;}
    /* W152: the shader reads layers by GPU address (GL_EXT_buffer_reference) */
    /* W153: with 64-bit integers (the address arithmetic) and the compiled code readable
     * (pipeline_init looks for FLAT instructions in it) */
    VkPhysicalDevicePipelineExecutablePropertiesFeaturesKHR executables={
        .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_EXECUTABLE_PROPERTIES_FEATURES_KHR};
    VkPhysicalDeviceBufferDeviceAddressFeatures addressing={
        .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_BUFFER_DEVICE_ADDRESS_FEATURES,.pNext=&executables};
    VkPhysicalDeviceFeatures2 features={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,.pNext=&addressing};
    vkGetPhysicalDeviceFeatures2(gpu,&features);
    if(!addressing.bufferDeviceAddress || !features.features.shaderInt64 || !executables.pipelineExecutableInfo) {
        fprintf(stderr,"PWSINK gpu_failed bufferDeviceAddress=%u shaderInt64=%u pipelineExecutableInfo=%u\n",
                addressing.bufferDeviceAddress,features.features.shaderInt64,executables.pipelineExecutableInfo);
        return -1;
    }
    executables=(VkPhysicalDevicePipelineExecutablePropertiesFeaturesKHR){
        .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_EXECUTABLE_PROPERTIES_FEATURES_KHR,.pipelineExecutableInfo=VK_TRUE};
    addressing=(VkPhysicalDeviceBufferDeviceAddressFeatures){
        .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_BUFFER_DEVICE_ADDRESS_FEATURES,.pNext=&executables,.bufferDeviceAddress=VK_TRUE};
    VkPhysicalDeviceFeatures enabled={.shaderInt64=VK_TRUE};
    static const char *const extensions[]={VK_KHR_BUFFER_DEVICE_ADDRESS_EXTENSION_NAME,
                                          VK_KHR_PIPELINE_EXECUTABLE_PROPERTIES_EXTENSION_NAME};
    float priority=1.0f;
    VkDeviceQueueCreateInfo queue_info={.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueFamilyIndex=family,
                                        .queueCount=1,.pQueuePriorities=&priority};
    VkDeviceCreateInfo device_info={.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.pNext=&addressing,.queueCreateInfoCount=1,
                                    .pQueueCreateInfos=&queue_info,.enabledExtensionCount=2,.ppEnabledExtensionNames=extensions,
                                    .pEnabledFeatures=&enabled};
    TRY(vkCreateDevice(gpu,&device_info,NULL,&device));
#define LOAD(name) name=(PFN_##name)vk_common_GetDeviceProcAddr(device,#name); \
    if(!name) {fprintf(stderr,"PWSINK gpu_failed no %s\n",#name);return -1;}
    DEVICE_FUNCTIONS(LOAD)
#undef LOAD
    vkGetDeviceQueue(device,family,0,&queue);
    state=1;
    return 0;
}
static uint32_t memory_type(uint32_t allowed,VkMemoryPropertyFlags want)
{
    for(uint32_t t=0;t<memory.memoryTypeCount;++t)
        if((allowed&(1u<<t)) && (memory.memoryTypes[t].propertyFlags&want)==want) return t;
    return UINT32_MAX;
}
/* a mapped buffer; *type gets the memory type */
static int mapped_buffer(VkDeviceSize bytes,VkBufferUsageFlags usage,VkMemoryPropertyFlags want,VkBuffer *buffer,
                         void **data,uint32_t *type)
{
    VkBufferCreateInfo info={.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=bytes,.usage=usage};
    VkMemoryAllocateFlagsInfo flags={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_FLAGS_INFO,
                                     .flags=VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT};
    TRY(vkCreateBuffer(device,&info,NULL,buffer));
    VkMemoryRequirements req;vkGetBufferMemoryRequirements(device,*buffer,&req);
    *type=memory_type(req.memoryTypeBits,want);
    if(*type==UINT32_MAX) {fprintf(stderr,"PWSINK gpu_failed no memory type 0x%x\n",(unsigned)want);return -1;}
    VkMemoryAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .pNext=usage&VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT?&flags:NULL,.allocationSize=req.size,.memoryTypeIndex=*type};
    VkDeviceMemory backing;
    TRY(vkAllocateMemory(device,&alloc,NULL,&backing));
    TRY(vkBindBufferMemory(device,*buffer,backing,0));
    TRY(vkMapMemory(device,backing,0,VK_WHOLE_SIZE,0,data));
    return 0;
}
/* the pool and the layer list, once */
static int pool_init(void)
{
    static int state;
    if(state) return state>0?0:-1;
    state=-1;
    if(device_init()) return -1;
    pool_bytes=POOL_BYTES;
    if(pool_bytes/4>max_texels) pool_bytes=(size_t)max_texels*4/POOL_ALIGN*POOL_ALIGN;
    /* GDI reads and writes the pool: CPU-cached memory, which the GPU reads coherently */
    VkBuffer pool_buffer;uint32_t type;
    if(mapped_buffer(pool_bytes,VK_BUFFER_USAGE_UNIFORM_TEXEL_BUFFER_BIT|VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT,
                     VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|
                     VK_MEMORY_PROPERTY_HOST_COHERENT_BIT|VK_MEMORY_PROPERTY_HOST_CACHED_BIT,&pool_buffer,(void **)&pool,&type))
        return -1;
    VkBufferViewCreateInfo view={.sType=VK_STRUCTURE_TYPE_BUFFER_VIEW_CREATE_INFO,.buffer=pool_buffer,
                                 .format=VK_FORMAT_R32_UINT,.range=VK_WHOLE_SIZE};
    TRY(vkCreateBufferView(device,&view,NULL,&pool_view));
    VkBufferDeviceAddressInfo address={.sType=VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO,.buffer=pool_buffer};
    pool_address=vkGetBufferDeviceAddressKHR(device,&address);
    images=pool_address==(uint64_t)(uintptr_t)pool;
    fprintf(stderr,"PWSINK gpu_address pool cpu=%p gpu=0x%llx images=%d\n",(void *)pool,(unsigned long long)pool_address,images);
    uint32_t layer_type;
    if(mapped_buffer(sizeof(*layer_data)*MAX_LAYERS,VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|
                     VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,&layer_buffer,(void **)&layer_data,&layer_type))
        return -1;
    fprintf(stderr,"PWSINK gpu_pool bytes=%zu memory_type=%u at %p max_texels=%u\n",pool_bytes,type,(void *)pool,
            (unsigned)max_texels);
    state=1;
    return 0;
}

/* 1 when a layer may be an image outside the pool, given by its CPU address (W152) */
int pw_sink_gpu_images(void);
int pw_sink_gpu_images(void)
{
    return !pool_init() && images;
}

/* Pool memory for window contents (W144), first fit; NULL when the pool is full. */
void *pw_sink_gpu_alloc(size_t bytes);
void *pw_sink_gpu_alloc(size_t bytes)
{
    if(!bytes || pool_init() || block_count==POOL_BLOCKS) return NULL;
    bytes=(bytes+POOL_ALIGN-1)/POOL_ALIGN*POOL_ALIGN;
    size_t at=0;unsigned i;
    for(i=0;i<block_count;++i) {
        if(blocks[i].at-at>=bytes) break;
        at=blocks[i].at+blocks[i].bytes;
    }
    if(at>pool_bytes || pool_bytes-at<bytes) {
        fprintf(stderr,"PWSINK gpu_pool_full want=%zu blocks=%u\n",bytes,block_count);
        return NULL;
    }
    memmove(&blocks[i+1],&blocks[i],(block_count-i)*sizeof(*blocks));
    blocks[i].at=at;blocks[i].bytes=bytes;++block_count;
    return pool+at;
}
/* 1 when pixels was pool memory (now free), 0 when it is not the pool's */
int pw_sink_gpu_free(void *pixels);
int pw_sink_gpu_free(void *pixels)
{
    uint8_t *at=pixels;
    if(!pool || at<pool || at>=pool+pool_bytes) return 0;
    for(unsigned i=0;i<block_count;++i)
        if(pool+blocks[i].at==at) {
            memmove(&blocks[i],&blocks[i+1],(block_count-i-1)*sizeof(*blocks));
            --block_count;
            return 1;
        }
    fprintf(stderr,"PWSINK gpu_pool_bad_free %p\n",pixels);
    return 1;
}
/* The desktop win32u composes into when the GPU does not stack its windows (W142). */
void *pw_sink_gpu_screen(unsigned width,unsigned height);
void *pw_sink_gpu_screen(unsigned width,unsigned height)
{
    if(screen) return screen;
    if(!(screen=pw_sink_gpu_alloc((size_t)width*height*4))) return NULL;
    memset(screen,0,(size_t)width*height*4);
    screen_width=width;screen_height=height;
    fprintf(stderr,"PWSINK gpu_screen %ux%u at %p\n",width,height,screen);
    return screen;
}

/* the pipeline with the fragment shader code (W153: two builds of screen.frag) */
static int make_pipeline(const uint32_t *code,size_t size,VkPipelineCreateFlags flags)
{
    static VkShaderModule vs;
    VkShaderModule fs;
    VkShaderModuleCreateInfo module={.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,.codeSize=sizeof(screen_vert),
                                     .pCode=screen_vert};
    if(!vs) TRY(vkCreateShaderModule(device,&module,NULL,&vs));
    module.codeSize=size;module.pCode=code;
    TRY(vkCreateShaderModule(device,&module,NULL,&fs));
    VkPipelineShaderStageCreateInfo stages[2]={
        {.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,.stage=VK_SHADER_STAGE_VERTEX_BIT,.module=vs,.pName="main"},
        {.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,.stage=VK_SHADER_STAGE_FRAGMENT_BIT,.module=fs,.pName="main"}};
    VkPipelineVertexInputStateCreateInfo vertex={.sType=VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
    VkPipelineInputAssemblyStateCreateInfo assembly={.sType=VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
                                                     .topology=VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST};
    VkPipelineViewportStateCreateInfo viewport={.sType=VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
                                                .viewportCount=1,.scissorCount=1};
    VkPipelineRasterizationStateCreateInfo raster={.sType=VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
                                                   .polygonMode=VK_POLYGON_MODE_FILL,.cullMode=VK_CULL_MODE_NONE,.lineWidth=1.0f};
    VkPipelineMultisampleStateCreateInfo multisample={.sType=VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
                                                      .rasterizationSamples=VK_SAMPLE_COUNT_1_BIT};
    VkPipelineColorBlendAttachmentState blend={.colorWriteMask=0xf};
    VkPipelineColorBlendStateCreateInfo blending={.sType=VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
                                                  .attachmentCount=1,.pAttachments=&blend};
    VkDynamicState dynamic[2]={VK_DYNAMIC_STATE_VIEWPORT,VK_DYNAMIC_STATE_SCISSOR};
    VkPipelineDynamicStateCreateInfo dynamics={.sType=VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO,
                                               .dynamicStateCount=2,.pDynamicStates=dynamic};
    VkGraphicsPipelineCreateInfo info={.sType=VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,.stageCount=2,.pStages=stages,
        .pVertexInputState=&vertex,.pInputAssemblyState=&assembly,.pViewportState=&viewport,.pRasterizationState=&raster,
        .pMultisampleState=&multisample,.pColorBlendState=&blending,.pDynamicState=&dynamics,.layout=layout,.renderPass=pass,
        .flags=flags};
    TRY(vkCreateGraphicsPipelines(device,VK_NULL_HANDLE,1,&info,NULL,&pipeline));
    return 0;
}

/* W153: 1 when the pipeline's compiled code has a FLAT memory instruction (ACO's IR and
 * disassembly name them flat_*), 0 when it has none, -1 when RADV gave no code to look at */
static int uses_flat(void)
{
    VkPipelineInfoKHR info={.sType=VK_STRUCTURE_TYPE_PIPELINE_INFO_KHR,.pipeline=pipeline};
    VkPipelineExecutablePropertiesKHR properties[4];
    uint32_t count=4,looked=0;
    for(uint32_t i=0;i<count;++i) properties[i]=(VkPipelineExecutablePropertiesKHR){
        .sType=VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_PROPERTIES_KHR};
    VkResult r=vkGetPipelineExecutablePropertiesKHR(device,&info,&count,properties);
    if(r!=VK_SUCCESS && r!=VK_INCOMPLETE) {fprintf(stderr,"PWSINK gpu_images executables = %d\n",(int)r);return -1;}
    for(uint32_t e=0;e<count;++e) {
        if(!(properties[e].stages&VK_SHADER_STAGE_FRAGMENT_BIT)) continue;
        VkPipelineExecutableInfoKHR which={.sType=VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INFO_KHR,.pipeline=pipeline,
                                           .executableIndex=e};
        VkPipelineExecutableInternalRepresentationKHR texts[8];
        uint32_t text_count=8;
        for(uint32_t i=0;i<text_count;++i) texts[i]=(VkPipelineExecutableInternalRepresentationKHR){
            .sType=VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INTERNAL_REPRESENTATION_KHR};
        /* first the sizes, then the texts into one arena (cut short, VK_INCOMPLETE, if too long) */
        r=vkGetPipelineExecutableInternalRepresentationsKHR(device,&which,&text_count,texts);
        if(r!=VK_SUCCESS && r!=VK_INCOMPLETE) {fprintf(stderr,"PWSINK gpu_images representations = %d\n",(int)r);return -1;}
        static char arena[1<<20];
        size_t used=0;
        for(uint32_t t=0;t<text_count;++t) {
            if(texts[t].dataSize>sizeof(arena)-used) texts[t].dataSize=sizeof(arena)-used;
            texts[t].pData=arena+used;used+=texts[t].dataSize;
        }
        r=vkGetPipelineExecutableInternalRepresentationsKHR(device,&which,&text_count,texts);
        if(r!=VK_SUCCESS && r!=VK_INCOMPLETE) {fprintf(stderr,"PWSINK gpu_images texts = %d\n",(int)r);return -1;}
        for(uint32_t t=0;t<text_count;++t) {
            const char *text=texts[t].pData;
            size_t size=texts[t].dataSize;
            if(!texts[t].isText || !size) continue;
            fprintf(stderr,"PWSINK gpu_images looked at '%s' (%zu bytes)\n",texts[t].name,size);
            ++looked;
            for(size_t c=0;c+5<=size;++c) if(!memcmp(text+c,"flat_",5)) return 1;
        }
    }
    return looked?0:-1;
}

static int pipeline_init(void)
{
    if(pool_init()) return -1;
    VkAttachmentDescription attachment={.format=out_format,.samples=VK_SAMPLE_COUNT_1_BIT,
        .loadOp=VK_ATTACHMENT_LOAD_OP_DONT_CARE,.storeOp=VK_ATTACHMENT_STORE_OP_STORE,
        .stencilLoadOp=VK_ATTACHMENT_LOAD_OP_DONT_CARE,.stencilStoreOp=VK_ATTACHMENT_STORE_OP_DONT_CARE,
        .initialLayout=VK_IMAGE_LAYOUT_UNDEFINED,.finalLayout=VK_IMAGE_LAYOUT_GENERAL};
    VkAttachmentReference reference={0,VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkSubpassDescription subpass={.pipelineBindPoint=VK_PIPELINE_BIND_POINT_GRAPHICS,.colorAttachmentCount=1,
                                  .pColorAttachments=&reference};
    VkRenderPassCreateInfo pass_info={.sType=VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,.attachmentCount=1,
                                      .pAttachments=&attachment,.subpassCount=1,.pSubpasses=&subpass};
    TRY(vkCreateRenderPass(device,&pass_info,NULL,&pass));

    VkDescriptorSetLayoutBinding bindings[2]={
        {0,VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER,1,VK_SHADER_STAGE_FRAGMENT_BIT,NULL},
        {1,VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,1,VK_SHADER_STAGE_FRAGMENT_BIT,NULL}};
    VkDescriptorSetLayoutCreateInfo set_info={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
                                              .bindingCount=2,.pBindings=bindings};
    VkDescriptorSetLayout set_layout;
    TRY(vkCreateDescriptorSetLayout(device,&set_info,NULL,&set_layout));
    VkDescriptorPoolSize sizes[2]={{VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER,1},{VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,1}};
    VkDescriptorPoolCreateInfo pool_info={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,.maxSets=1,
                                          .poolSizeCount=2,.pPoolSizes=sizes};
    VkDescriptorPool descriptors;
    TRY(vkCreateDescriptorPool(device,&pool_info,NULL,&descriptors));
    VkDescriptorSetAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,.descriptorPool=descriptors,
                                       .descriptorSetCount=1,.pSetLayouts=&set_layout};
    TRY(vkAllocateDescriptorSets(device,&alloc,&set));
    VkDescriptorBufferInfo layer_info={layer_buffer,0,VK_WHOLE_SIZE};
    VkWriteDescriptorSet writes[2]={
        {.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,.dstSet=set,.dstBinding=0,.descriptorCount=1,
         .descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER,.pTexelBufferView=&pool_view},
        {.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,.dstSet=set,.dstBinding=1,.descriptorCount=1,
         .descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,.pBufferInfo=&layer_info}};
    vkUpdateDescriptorSets(device,2,writes,0,NULL);

    VkPushConstantRange range={VK_SHADER_STAGE_FRAGMENT_BIT,0,9*sizeof(int32_t)};
    VkPipelineLayoutCreateInfo layout_info={.sType=VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,.setLayoutCount=1,
                                            .pSetLayouts=&set_layout,.pushConstantRangeCount=1,.pPushConstantRanges=&range};
    TRY(vkCreatePipelineLayout(device,&layout_info,NULL,&layout));
    if(images && !make_pipeline(screen_frag,sizeof(screen_frag),VK_PIPELINE_CREATE_CAPTURE_INTERNAL_REPRESENTATIONS_BIT_KHR)) {
        int flat=uses_flat();
        if(!flat) {fprintf(stderr,"PWSINK gpu_images shader=address flat=0\n");goto commands;}
        fprintf(stderr,"PWSINK gpu_images off: the compiled shader %s\n",flat>0?"uses FLAT":"could not be checked");
    } else if(images) fprintf(stderr,"PWSINK gpu_images off: no pipeline with image layers\n");
    images=0;
    if(make_pipeline(screen_frag_pool,sizeof(screen_frag_pool),0)) return -1;
commands:;

    VkCommandPoolCreateInfo command_info={.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                          .flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,.queueFamilyIndex=family};
    VkCommandPool commands;
    TRY(vkCreateCommandPool(device,&command_info,NULL,&commands));
    VkCommandBufferAllocateInfo cmd_info={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=commands,
                                          .level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=1};
    TRY(vkAllocateCommandBuffers(device,&cmd_info,&cmd));
    VkFenceCreateInfo fence_info={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    TRY(vkCreateFence(device,&fence_info,NULL,&fence));
    return 0;
}

/* The two VideoOut buffers, registered on video. *pixels and *pitch (in pixels) let the sink
 * fall back to its CPU copy into the same buffers. */
int pw_sink_gpu_buffers(int video,unsigned width,unsigned height,uint32_t **pixels,unsigned *pitch);
int pw_sink_gpu_buffers(int video,unsigned width,unsigned height,uint32_t **pixels,unsigned *pitch)
{
    if(device_init() || pipeline_init()) return -1;
    void *addresses[BUFFERS];unsigned row=0;
    for(int i=0;i<BUFFERS;++i) {
        VkImageCreateInfo info={.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,.imageType=VK_IMAGE_TYPE_2D,.format=out_format,
            .extent={width,height,1},.mipLevels=1,.arrayLayers=1,.samples=VK_SAMPLE_COUNT_1_BIT,
            .tiling=VK_IMAGE_TILING_LINEAR,.usage=VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,
            .initialLayout=VK_IMAGE_LAYOUT_UNDEFINED};
        VkImage image;
        TRY(vkCreateImage(device,&info,NULL,&image));
        VkMemoryRequirements req;vkGetImageMemoryRequirements(device,image,&req);
        uint32_t type=memory_type(req.memoryTypeBits,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT|
                                  VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        if(type==UINT32_MAX) {fprintf(stderr,"PWSINK gpu_failed no device-local host-visible memory type\n");return -1;}
        /* VideoOut wants 2 MiB aligned buffers: over-allocate and bind at an aligned offset */
        const VkDeviceSize slack=2<<20;
        VkMemoryAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.allocationSize=req.size+slack,
                                    .memoryTypeIndex=type};
        VkDeviceMemory backing;uint8_t *base;
        TRY(vkAllocateMemory(device,&alloc,NULL,&backing));
        TRY(vkMapMemory(device,backing,0,VK_WHOLE_SIZE,0,(void **)&base));
        VkDeviceSize offset=((uintptr_t)base+slack-1)/slack*slack-(uintptr_t)base;
        offset=(offset+req.alignment-1)/req.alignment*req.alignment;
        TRY(vkBindImageMemory(device,image,backing,offset));
        VkImageSubresource subresource={VK_IMAGE_ASPECT_COLOR_BIT,0,0};
        VkSubresourceLayout placed;vkGetImageSubresourceLayout(device,image,&subresource,&placed);
        addresses[i]=base+offset+placed.offset;pixels[i]=addresses[i];
        if(placed.rowPitch%4 || (i && row!=placed.rowPitch/4)) {fprintf(stderr,"PWSINK gpu_failed row pitch %llu\n",
            (unsigned long long)placed.rowPitch);return -1;}
        row=(unsigned)(placed.rowPitch/4);
        memset(addresses[i],0,(size_t)placed.rowPitch*height);
        VkImageViewCreateInfo view_info={.sType=VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,.image=image,
            .viewType=VK_IMAGE_VIEW_TYPE_2D,.format=out_format,.subresourceRange={VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,1}};
        VkImageView view;
        TRY(vkCreateImageView(device,&view_info,NULL,&view));
        VkFramebufferCreateInfo fb={.sType=VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,.renderPass=pass,.attachmentCount=1,
                                    .pAttachments=&view,.width=width,.height=height,.layers=1};
        TRY(vkCreateFramebuffer(device,&fb,NULL,&framebuffers[i]));
        fprintf(stderr,"PWSINK gpu_buffer %d memory_type=%u at %p row_pitch=%llu\n",i,type,addresses[i],
                (unsigned long long)placed.rowPitch);
    }
    OrbisVideoOutBufferAttribute attribute;memset(&attribute,0,sizeof(attribute));
    sceVideoOutSetBufferAttribute(&attribute,FORMAT_A8R8G8B8_SRGB,TILING_LINEAR,0,width,height,row);
    int rc=sceVideoOutRegisterBuffers(video,0,addresses,BUFFERS,&attribute);
    if(rc) {fprintf(stderr,"PWSINK gpu_failed register rc=%x\n",rc);return -1;}
    out_width=width;out_height=height;*pitch=row;
    return 0;
}

/* Draws the layers (bottom first) of a width x height desktop, scaled into
 * left,top,scale_w,scale_h of buffer, and the pointer at cursor_x,cursor_y (output pixels);
 * waits until the GPU is done, so the sink can flip it. Every layer is pool memory, or (W152) an
 * image of source_width x source_height pixels scaled to its rect, when images are taken. */
int pw_sink_gpu_draw_layers(unsigned buffer,const struct layer *layers,unsigned count,unsigned width,unsigned height,
                            int left,int top,int scale_w,int scale_h,int cursor_x,int cursor_y);
int pw_sink_gpu_draw_layers(unsigned buffer,const struct layer *layers,unsigned count,unsigned width,unsigned height,
                            int left,int top,int scale_w,int scale_h,int cursor_x,int cursor_y)
{
    if(!out_width || buffer>=BUFFERS || count>MAX_LAYERS) return -1;
    for(unsigned i=0;i<count;++i) {
        const struct layer *l=&layers[i];
        const uint8_t *at=(const uint8_t *)l->pixels;
        size_t rows=l->bottom>l->top?(size_t)(l->bottom-l->top):0,columns=l->right>l->left?(size_t)(l->right-l->left):0;
        int32_t *d=layer_data[i];
        uint64_t address=pool_address;
        d[0]=l->left;d[1]=l->top;d[2]=l->right;d[3]=l->bottom;
        if(l->flags&LAYER_EXTERNAL) {
            if(!images || !at || (uintptr_t)at%4 || !l->source_width || !l->source_height || l->source_width>l->stride) {
                fprintf(stderr,"PWSINK gpu_failed image layer %u: %p %ux%u stride=%u images=%d\n",i,(const void *)at,
                        l->source_width,l->source_height,l->stride,images);
                return -1;
            }
            address=(uint64_t)(uintptr_t)at;
            d[4]=0;d[10]=(int32_t)l->source_width;d[11]=(int32_t)l->source_height;
        } else {
            if(at<pool || (size_t)(at-pool)%4 || columns>l->stride ||
               (rows && (size_t)(at-pool)+((rows-1)*l->stride+columns)*4>pool_bytes)) {
                fprintf(stderr,"PWSINK gpu_failed layer %u outside the pool: %p stride=%u\n",i,(const void *)at,l->stride);
                return -1;
            }
            d[4]=(int32_t)((size_t)(at-pool)/4);d[10]=(int32_t)columns;d[11]=(int32_t)rows;
        }
        d[5]=(int32_t)l->stride;d[6]=(int32_t)(l->flags&(LAYER_EXTERNAL|LAYER_RGBA));d[7]=0;
        /* the shader reads at this address for every layer: the pool's when it is not an image */
        d[8]=(int32_t)(uint32_t)address;d[9]=(int32_t)(uint32_t)(address>>32);
    }
    TRY(vkResetCommandBuffer(cmd,0));
    VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                    .flags=VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
    TRY(vkBeginCommandBuffer(cmd,&begin));
    VkRenderPassBeginInfo rp={.sType=VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,.renderPass=pass,
                              .framebuffer=framebuffers[buffer],.renderArea={{0,0},{out_width,out_height}}};
    vkCmdBeginRenderPass(cmd,&rp,VK_SUBPASS_CONTENTS_INLINE);
    vkCmdBindPipeline(cmd,VK_PIPELINE_BIND_POINT_GRAPHICS,pipeline);
    vkCmdBindDescriptorSets(cmd,VK_PIPELINE_BIND_POINT_GRAPHICS,layout,0,1,&set,0,NULL);
    VkViewport viewport={0,0,(float)out_width,(float)out_height,0,1};
    VkRect2D scissor={{0,0},{out_width,out_height}};
    vkCmdSetViewport(cmd,0,1,&viewport);vkCmdSetScissor(cmd,0,1,&scissor);
    int32_t push[9]={(int32_t)width,(int32_t)height,(int32_t)count,left,top,scale_w,scale_h,cursor_x,cursor_y};
    vkCmdPushConstants(cmd,layout,VK_SHADER_STAGE_FRAGMENT_BIT,0,sizeof(push),push);
    vkCmdDraw(cmd,3,1,0,0);
    vkCmdEndRenderPass(cmd);
    TRY(vkEndCommandBuffer(cmd));
    VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&cmd};
    TRY(vkQueueSubmit(queue,1,&submit,fence));
    TRY(vkWaitForFences(device,1,&fence,VK_TRUE,1000000000ull));
    TRY(vkResetFences(device,1,&fence));
    return 0;
}

/* The desktop of pw_sink_gpu_screen as one layer (W142). */
int pw_sink_gpu_draw(unsigned buffer,unsigned stride,int left,int top,int scale_w,int scale_h,int cursor_x,int cursor_y);
int pw_sink_gpu_draw(unsigned buffer,unsigned stride,int left,int top,int scale_w,int scale_h,int cursor_x,int cursor_y)
{
    if(!screen || stride%4) return -1;
    struct layer desktop={screen,0,0,(int)screen_width,(int)screen_height,stride/4,0,screen_width,screen_height};
    return pw_sink_gpu_draw_layers(buffer,&desktop,1,screen_width,screen_height,left,top,scale_w,scale_h,cursor_x,cursor_y);
}
