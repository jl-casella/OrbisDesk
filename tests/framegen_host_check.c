/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Frame generation host check (docs/FRAME_GENERATION.md): the four compute passes of native/hw_sink_gpu
 * (fg_capture, fg_coarse, fg_fine, fg_blend), as SPIR-V from the same sources, run on a host Vulkan device
 * (Mesa's lavapipe) over synthetic frames whose true midpoint is known:
 *   motion: a textured square moves (+12,+6) pixels over a textured static background;
 *   cut:    two unrelated frames;
 *   keep:   the motion again with a rectangle over the square (MangoHud's, stage 5), which must be the current frame.
 * It checks that the passes produce a frame closer to the true midpoint than the plain average of the two frames
 * and than repeating the current one, that the static background keeps zero motion, and that a cut falls back to
 * the current frame. This is host reference behaviour only: it says nothing about the PS4's GPU (FLAT,
 * timing), which framegen.inc.c checks and measures there. Run by tests/test_framegen_host.py. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>
#include "fg_capture_comp.h"
#include "fg_coarse_comp.h"
#include "fg_fine_comp.h"
#include "fg_blend_comp.h"

enum {W=320,H=192,BINDINGS=7};
struct push {uint32_t source[2],stride,rgba,size[2],luma[2],coarse[2],fine[2],keep[4];};  /* fg_common.glsl Push */
struct buffer {VkBuffer buffer;VkDeviceMemory memory;void *data;};
static VkDevice device;
static VkPhysicalDevice gpu;
static VkQueue queue;
static uint32_t family;
static PFN_vkGetBufferDeviceAddress get_address;

#define CHECK(call) do { VkResult r_=(call); if(r_!=VK_SUCCESS) {fprintf(stderr,"FAIL %s = %d\n",#call,(int)r_);exit(2);} } while(0)

static struct buffer make_buffer(VkDeviceSize bytes)
{
    struct buffer b;
    VkBufferCreateInfo info={.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=bytes,
                             .usage=VK_BUFFER_USAGE_STORAGE_BUFFER_BIT|VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT};
    CHECK(vkCreateBuffer(device,&info,NULL,&b.buffer));
    VkMemoryRequirements req;vkGetBufferMemoryRequirements(device,b.buffer,&req);
    VkPhysicalDeviceMemoryProperties props;vkGetPhysicalDeviceMemoryProperties(gpu,&props);
    uint32_t type=0,want=VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    while(type<props.memoryTypeCount && !((req.memoryTypeBits>>type&1) && (props.memoryTypes[type].propertyFlags&want)==want)) type++;
    VkMemoryAllocateFlagsInfo flags={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_FLAGS_INFO,.flags=VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT};
    VkMemoryAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.pNext=&flags,.allocationSize=req.size,.memoryTypeIndex=type};
    CHECK(vkAllocateMemory(device,&alloc,NULL,&b.memory));
    CHECK(vkBindBufferMemory(device,b.buffer,b.memory,0));
    CHECK(vkMapMemory(device,b.memory,0,VK_WHOLE_SIZE,0,&b.data));
    memset(b.data,0,bytes);
    return b;
}

/* deterministic texture: value noise in 4x4 pixel blocks, so block matching has something to match */
static uint32_t texel(uint32_t seed,int x,int y)
{
    uint32_t h=seed^(uint32_t)(x/4)*0x9e3779b1u^(uint32_t)(y/4)*0x85ebca77u;
    h^=h>>15;h*=0x2c1b3c6du;h^=h>>12;h*=0x297a2d39u;h^=h>>15;
    uint32_t r=40+(h&0x7f),g=40+((h>>8)&0x7f),b=40+((h>>16)&0x7f);
    return r|g<<8|b<<16|0xffu<<24;   /* R,G,B,A in memory: rgba=1 */
}
/* the background, and a 64x64 square of another texture with its corner at sx,sy (texture moves with it) */
static void scene(uint32_t *out,double sx,double sy)
{
    for(int y=0;y<H;y++)
        for(int x=0;x<W;x++) {
            double u=x-sx,v=y-sy;
            out[y*W+x]=u>=0 && v>=0 && u<64 && v<64?texel(7,(int)u+64,(int)v+64):texel(1,x,y);
        }
}
static double difference(const uint32_t *a,const uint32_t *b,int margin)
{
    double sum=0;int n=0;
    for(int y=margin;y<H-margin;y++)
        for(int x=margin;x<W-margin;x++,n++)
            for(int c=0;c<3;c++) sum+=fabs((double)((a[y*W+x]>>(8*c))&0xff)-(double)((b[y*W+x]>>(8*c))&0xff));
    return sum/n/3;
}

int main(void)
{
    VkApplicationInfo app={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.apiVersion=VK_API_VERSION_1_2};
    VkInstanceCreateInfo instance_info={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app};
    VkInstance instance;CHECK(vkCreateInstance(&instance_info,NULL,&instance));
    uint32_t count=1;VkResult r=vkEnumeratePhysicalDevices(instance,&count,&gpu);
    if((r!=VK_SUCCESS && r!=VK_INCOMPLETE) || !count) {fprintf(stderr,"FAIL no Vulkan device\n");return 2;}
    VkPhysicalDeviceProperties properties;vkGetPhysicalDeviceProperties(gpu,&properties);
    printf("device %s\n",properties.deviceName);
    VkQueueFamilyProperties families[8];count=8;vkGetPhysicalDeviceQueueFamilyProperties(gpu,&count,families);
    for(family=0;family<count && !(families[family].queueFlags&VK_QUEUE_COMPUTE_BIT);family++) {}
    VkPhysicalDeviceVulkan12Features v12={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES,.bufferDeviceAddress=VK_TRUE};
    VkPhysicalDeviceFeatures features={.shaderInt64=VK_TRUE};
    float priority=1;
    VkDeviceQueueCreateInfo queue_info={.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueFamilyIndex=family,.queueCount=1,
                                        .pQueuePriorities=&priority};
    VkDeviceCreateInfo device_info={.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.pNext=&v12,.queueCreateInfoCount=1,
                                    .pQueueCreateInfos=&queue_info,.pEnabledFeatures=&features};
    CHECK(vkCreateDevice(gpu,&device_info,NULL,&device));
    vkGetDeviceQueue(device,family,0,&queue);
    get_address=(PFN_vkGetBufferDeviceAddress)vkGetDeviceProcAddr(device,"vkGetBufferDeviceAddress");

    struct push p={.stride=W,.rgba=1,.size={W,H},.luma={(W+1)/2,(H+1)/2}};
    p.coarse[0]=(p.luma[0]+7)/8;p.coarse[1]=(p.luma[1]+7)/8;p.fine[0]=(p.luma[0]+3)/4;p.fine[1]=(p.luma[1]+3)/4;
    VkDeviceSize color=(VkDeviceSize)W*H*4,luma=(VkDeviceSize)p.luma[0]*p.luma[1]*4;
    struct buffer source=make_buffer(color),colors[2]={make_buffer(color),make_buffer(color)},lumas[2]={make_buffer(luma),make_buffer(luma)},
                  coarse=make_buffer((VkDeviceSize)p.coarse[0]*p.coarse[1]*16),fine=make_buffer((VkDeviceSize)p.fine[0]*p.fine[1]*16),
                  outs[2]={make_buffer(color),make_buffer(color)};
    VkBufferDeviceAddressInfo address_info={.sType=VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO,.buffer=source.buffer};
    uint64_t address=get_address(device,&address_info);
    p.source[0]=(uint32_t)address;p.source[1]=(uint32_t)(address>>32);

    VkDescriptorSetLayoutBinding bindings[BINDINGS];
    for(uint32_t i=0;i<BINDINGS;i++) bindings[i]=(VkDescriptorSetLayoutBinding){i,VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1,VK_SHADER_STAGE_COMPUTE_BIT,NULL};
    VkDescriptorSetLayoutCreateInfo set_info={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,.bindingCount=BINDINGS,.pBindings=bindings};
    VkDescriptorSetLayout set_layout;CHECK(vkCreateDescriptorSetLayout(device,&set_info,NULL,&set_layout));
    VkPushConstantRange range={VK_SHADER_STAGE_COMPUTE_BIT,0,sizeof(p)};
    VkPipelineLayoutCreateInfo layout_info={.sType=VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,.setLayoutCount=1,.pSetLayouts=&set_layout,
                                            .pushConstantRangeCount=1,.pPushConstantRanges=&range};
    VkPipelineLayout layout;CHECK(vkCreatePipelineLayout(device,&layout_info,NULL,&layout));
    const struct {const uint32_t *code;size_t size;} spirv[4]={{fg_capture_comp,sizeof(fg_capture_comp)},{fg_coarse_comp,sizeof(fg_coarse_comp)},
                                                               {fg_fine_comp,sizeof(fg_fine_comp)},{fg_blend_comp,sizeof(fg_blend_comp)}};
    VkPipeline pipelines[4];
    for(int i=0;i<4;i++) {
        VkShaderModuleCreateInfo module_info={.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,.codeSize=spirv[i].size,.pCode=spirv[i].code};
        VkShaderModule module;CHECK(vkCreateShaderModule(device,&module_info,NULL,&module));
        VkComputePipelineCreateInfo info={.sType=VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
            .stage={.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,.stage=VK_SHADER_STAGE_COMPUTE_BIT,.module=module,.pName="main"},
            .layout=layout};
        CHECK(vkCreateComputePipelines(device,VK_NULL_HANDLE,1,&info,NULL,&pipelines[i]));
    }
    VkDescriptorPoolSize size={VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,2*BINDINGS};
    VkDescriptorPoolCreateInfo pool_info={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,.maxSets=2,.poolSizeCount=1,.pPoolSizes=&size};
    VkDescriptorPool pool;CHECK(vkCreateDescriptorPool(device,&pool_info,NULL,&pool));
    VkDescriptorSetLayout layouts[2]={set_layout,set_layout};
    VkDescriptorSetAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,.descriptorPool=pool,.descriptorSetCount=2,.pSetLayouts=layouts};
    VkDescriptorSet sets[2];CHECK(vkAllocateDescriptorSets(device,&alloc,sets));
    for(int s=0;s<2;s++) {
        const struct buffer *bound[BINDINGS]={&colors[s],&lumas[s],&colors[1-s],&lumas[1-s],&coarse,&fine,&outs[s]};
        VkDescriptorBufferInfo infos[BINDINGS];VkWriteDescriptorSet writes[BINDINGS];
        for(int i=0;i<BINDINGS;i++) {
            infos[i]=(VkDescriptorBufferInfo){bound[i]->buffer,0,VK_WHOLE_SIZE};
            writes[i]=(VkWriteDescriptorSet){.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,.dstSet=sets[s],.dstBinding=(uint32_t)i,.descriptorCount=1,
                                             .descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.pBufferInfo=&infos[i]};
        }
        vkUpdateDescriptorSets(device,BINDINGS,writes,0,NULL);
    }
    VkCommandPoolCreateInfo command_info={.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
                                          .queueFamilyIndex=family};
    VkCommandPool commands;CHECK(vkCreateCommandPool(device,&command_info,NULL,&commands));
    VkCommandBufferAllocateInfo cmd_info={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=commands,
                                          .level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=1};
    VkCommandBuffer cmd;CHECK(vkAllocateCommandBuffers(device,&cmd_info,&cmd));

    VkFenceCreateInfo fence_info={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence copied,done;CHECK(vkCreateFence(device,&fence_info,NULL,&copied));CHECK(vkCreateFence(device,&fence_info,NULL,&done));

    /* one frame through the passes, as framegen.inc.c (04.19) records them: the capture into slot alone in one
     * submission whose fence is waited for, then (generate) a second submission that starts with a barrier (ordering
     * it after the copy, earlier on the same queue) and runs the rest */
    #define RUN(slot,generate) do { \
        VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO}; \
        const uint32_t grid[4][2]={{p.luma[0],p.luma[1]},{p.coarse[0],p.coarse[1]},{p.fine[0],p.fine[1]},{W,H}}; \
        VkMemoryBarrier barrier={.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER,.srcAccessMask=VK_ACCESS_SHADER_WRITE_BIT, \
                                 .dstAccessMask=VK_ACCESS_SHADER_READ_BIT}; \
        for(int part=0;part<((generate)?2:1);part++) { \
            CHECK(vkResetCommandBuffer(cmd,0));CHECK(vkBeginCommandBuffer(cmd,&begin)); \
            for(int pass=part?1:0;pass<(part?4:1);pass++) { \
                if(pass) vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,0,1,&barrier,0,NULL,0,NULL); \
                vkCmdBindPipeline(cmd,VK_PIPELINE_BIND_POINT_COMPUTE,pipelines[pass]); \
                vkCmdBindDescriptorSets(cmd,VK_PIPELINE_BIND_POINT_COMPUTE,layout,0,1,&sets[slot],0,NULL); \
                vkCmdPushConstants(cmd,layout,VK_SHADER_STAGE_COMPUTE_BIT,0,sizeof(p),&p); \
                vkCmdDispatch(cmd,(grid[pass][0]+7)/8,(grid[pass][1]+7)/8,1); \
            } \
            CHECK(vkEndCommandBuffer(cmd)); \
            VkFence fence=part?done:copied; \
            VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&cmd}; \
            CHECK(vkQueueSubmit(queue,1,&submit,fence)); \
            CHECK(vkWaitForFences(device,1,&fence,VK_TRUE,1000000000ull));CHECK(vkResetFences(device,1,&fence)); \
        } } while(0)

    static uint32_t before[W*H],after[W*H],truth[W*H],average[W*H];
    int failures=0;

    /* motion: the square from (80,60) to (92,66); truth is the scene at (86,63) */
    scene(before,80,60);scene(after,92,66);scene(truth,86,63);
    memcpy(source.data,before,color);RUN(0,0);
    memcpy(source.data,after,color);RUN(1,1);
    if(memcmp(colors[1].data,after,color) || memcmp(colors[0].data,before,color)) {printf("FAIL capture: history differs from the source\n");failures++;}
    for(int i=0;i<W*H;i++) {
        uint32_t a=before[i],b=after[i],v=0;
        for(int c=0;c<4;c++) v|=((((a>>(8*c))&0xff)+((b>>(8*c))&0xff)+1)/2)<<(8*c);
        average[i]=v;
    }
    const uint32_t *generated=outs[1].data;
    double e_generated=difference(generated,truth,8),e_average=difference(average,truth,8),e_repeat=difference(after,truth,8);
    printf("motion: mean abs error vs true midpoint: generated=%.2f average=%.2f repeat=%.2f\n",e_generated,e_average,e_repeat);
    if(!(e_generated<0.5*e_average && e_generated<0.5*e_repeat)) {printf("FAIL motion: generated frame not clearly closer to the midpoint\n");failures++;}
    const float *field=fine.data;
    /* a fine cell inside the square's path (luma 46..56 x 36..44 → cell 12,9) and one far in the background */
    const float *moving=field+4*(9*p.fine[0]+12),*still=field+4*(2*p.fine[0]+2);
    printf("motion: fine field in the square %.2f,%.2f (expect 6,3 texels) err=%.3f; background %.2f,%.2f err=%.3f\n",
           moving[0],moving[1],moving[2],still[0],still[1],still[2]);
    if(fabsf(moving[0]-6)>0.75f || fabsf(moving[1]-3)>0.75f) {printf("FAIL motion: wrong vector in the square\n");failures++;}
    if(fabsf(still[0])>0.01f || fabsf(still[1])>0.01f) {printf("FAIL motion: static background moved\n");failures++;}

    /* cut: two unrelated textures; the output must be close to the current frame (fallback), not a mix */
    for(int i=0;i<W*H;i++) {before[i]=texel(3,i%W,i/W);after[i]=texel(11,i%W,i/W);}
    memcpy(source.data,before,color);RUN(0,0);
    memcpy(source.data,after,color);RUN(1,1);
    double e_cut=difference(generated,after,8);
    printf("cut: generated vs current frame %.2f (0 = full fallback)\n",e_cut);
    if(e_cut>4.0) {printf("FAIL cut: no fallback to the current frame\n");failures++;}

    /* keep (stage 5): the motion again, with a rectangle over the square's path: inside it the generated frame is the
     * current one word for word; the rest is still generated */
    enum {KX0=60,KY0=40,KX1=140,KY1=110};
    p.keep[0]=KX0;p.keep[1]=KY0;p.keep[2]=KX1;p.keep[3]=KY1;
    scene(before,80,60);scene(after,92,66);
    memcpy(source.data,before,color);RUN(0,0);
    memcpy(source.data,after,color);RUN(1,1);
    unsigned kept_wrong=0,outside_generated=0;
    for(int y=0;y<H;y++)
        for(int x=0;x<W;x++) {
            int inside=x>=KX0 && x<KX1 && y>=KY0 && y<KY1;
            if(inside && generated[y*W+x]!=after[y*W+x]) kept_wrong++;
            if(!inside && generated[y*W+x]!=after[y*W+x]) outside_generated++;
        }
    printf("keep: pixels in the rectangle that differ from the current frame %u (expect 0); generated pixels outside %u\n",
           kept_wrong,outside_generated);
    if(kept_wrong) {printf("FAIL keep: the rectangle was not taken from the current frame\n");failures++;}
    memset(p.keep,0,sizeof(p.keep));

    printf(failures?"FAILED %d checks\n":"PASS framegen host check\n",failures);
    return failures?1:0;
}
