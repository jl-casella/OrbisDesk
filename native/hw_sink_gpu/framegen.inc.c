/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Frame generation, stages 2 and 3 (docs/FRAME_GENERATION.md): an image-only interpolator on the sink's own
 * Vulkan device. Included at the end of hw_sink_gpu.c, whose device, queue, entry points and FLAT check it
 * uses; its compute shaders (fg_*.comp) are compiled to SPIR-V by the hardware build, like screen.frag.
 *
 * Stage 2, ownership. A presented image lives in the CPU buffer Mesa's headless WSI blits it into, one per
 * swapchain image (tools/vk-h0/patch-mesa-wsi.py), and the next present of that swapchain image overwrites it:
 * an address alone keeps nothing. So each present of the target swapchain is copied, on the presenting thread
 * and before its present returns (native/wine_vk_runtime.c pw_vk_present_hook), into one of two history slots
 * this file owns. The copy is a compute pass on the sink's queue that reads the WSI buffer by GPU address: the
 * game's device and the sink's are both RADV on one GPU, and nothing of the game's device (no image, view or
 * semaphore) is used here. The WSI waited for its blit before calling the hook, so the pixels are complete
 * when the copy reads them; the presenting thread returns only once the copy has run (below). Every later pass
 * reads owned memory only.
 *
 * The copy is its own submission with its own fence, and the presenting thread waits for that fence with
 * vkWaitForFences, the one wait the PS4 port proves every frame (the compositor's, hw_sink_gpu.c). 04.18 polled
 * a VkEvent set by the GPU after the copy instead; on the PS4 (W303 run-0217, NFS Underground 2) the event never
 * read as set within 1 s while the queue kept running, and events had never been used on this port before. Once
 * per run fg_probe submits an empty command buffer, the timestamp writes and an event set, each alone, and logs
 * how each one ended, so a console log tells which primitive fails.
 *
 * Stage 3, generation. A second submission starts with a barrier (it orders after the copy's, which is earlier
 * on the same queue) and runs motion estimation between frames N-1 and N (fg_coarse, fg_fine) and the frame
 * halfway between them (fg_blend), written to one of two owned outputs and timed with GPU timestamps. The
 * presenting thread does not wait for its fence; the next frame's copy does first, since it reuses N-1's slot,
 * and so does the sink's presenter before it shows the output. In "shadow" nothing shows the output; in
 * stage 4 the sink's presenter asks pw_sink_gpu_fg_pick for it and shows it on the vblank between two real frames
 * (platform/ps4/pw_wine_sink_ps4.c, pw_framegen_sched.h). Stage 5: the blend leaves a rectangle (MangoHud's) as
 * the current frame has it.
 *
 * The buffers are plain storage buffers (no image formats, so no format features to check); the source must be
 * one of the four 32-bit RGBA/BGRA formats the sink already shows. Any failure logs the Vulkan result, frees
 * everything this file made and turns generation off for the run; the sink keeps showing real frames. */
#include <pthread.h>
#include <errno.h>
#include <sched.h>
#include <sys/stat.h>
#include "fg_capture_comp.h"
#include "fg_coarse_comp.h"
#include "fg_fine_comp.h"
#include "fg_blend_comp.h"

extern uint64_t sceKernelGetProcessTime(void);
extern int pw_trace_level __attribute__((weak));   /* platform/ps4/pw_trace.h, not on this file's include path */
static int fg_trace(void) {return &pw_trace_level?pw_trace_level>0:1;}

#define FG_FUNCTIONS(X) X(vkCreateComputePipelines) X(vkCmdDispatch) X(vkCmdPipelineBarrier) X(vkCreateQueryPool) \
    X(vkCmdResetQueryPool) X(vkCmdWriteTimestamp) X(vkGetQueryPoolResults) X(vkCreateEvent) X(vkCmdSetEvent) \
    X(vkGetEventStatus) X(vkResetEvent) X(vkDestroyEvent) X(vkDestroyBuffer) X(vkFreeMemory) X(vkDestroyPipeline) \
    X(vkDestroyShaderModule) X(vkDestroyDescriptorPool) X(vkDestroyDescriptorSetLayout) X(vkDestroyPipelineLayout) \
    X(vkDestroyCommandPool) X(vkDestroyFence) X(vkDestroyQueryPool) X(vkGetFenceStatus)
#define DECLARE(name) static PFN_##name fg_##name;
FG_FUNCTIONS(DECLARE)
#undef DECLARE

enum {FG_PASSES=4,FG_CAPTURE=0,FG_COARSE,FG_FINE,FG_BLEND};
enum {FG_MAX_WIDTH=2560,FG_MAX_HEIGHT=1440,FG_SWITCH_US=500000,FG_REPORT=120,FG_DUMP_AT=90,FG_QUERIES=6,FG_BINDINGS=7,
      FG_WAIT_US=1000000,FG_COPY_LOGS=3,FG_EVENT_POLL_US=100000};
static const char *const fg_pass_names[FG_PASSES]={"capture","coarse","fine","blend"};
struct fg_buffer {VkBuffer buffer;VkDeviceMemory memory;void *data;VkDeviceSize bytes;};
struct fg_push {uint32_t source[2],stride,rgba,size[2],luma[2],coarse[2],fine[2],keep[4];};   /* fg_common.glsl Push */
static struct {
    int state;                                       /* 0 not tried, 1 ready, -1 off for the run */
    VkShaderModule modules[FG_PASSES];
    VkPipeline pipelines[FG_PASSES];
    VkDescriptorSetLayout set_layout;
    VkPipelineLayout layout;
    VkDescriptorPool descriptors;
    VkDescriptorSet sets[2];                         /* set s: current slot s, previous 1-s, output s */
    VkCommandPool commands;
    VkCommandBuffer copy_cmd,cmd;                    /* the copy's submission, the generation's */
    VkFence copied;                                  /* the copy's submission, waited for on the presenting thread */
    VkFence done;                                    /* the generation's submission */
    int copy_pending;                                /* the copy was submitted and its fence not yet seen signalled */
    uint64_t copies;                                 /* copies submitted this run (the first ones are logged) */
    VkQueryPool queries;                             /* VK_NULL_HANDLE: the queue has no timestamps */
    double tick_ns;
    uint64_t tick_mask;
    struct fg_buffer color[2],luma[2],coarse,fine,out[2];
    unsigned width,height;                           /* the buffers' frame size, 0 none */
    struct fg_push push;
    const void *target;                              /* the swapchain being followed */
    uint64_t target_us;
    uint64_t frames;                                 /* copies of the target since its history started */
    int in_flight;                                   /* a submission whose fence was not waited for yet */
    int in_flight_generates;                         /* and it generated (queries 2-5 written) */
    /* the current report: GPU time per pass, time the presenting thread spent here */
    uint64_t gpu_sum_ns[FG_PASSES],gpu_max_ns[FG_PASSES],block_sum_us,block_max_us;
    unsigned timed[FG_PASSES],blocks,generated,total_generated,dumped,refused;
    /* stage 4: what each history slot holds, for the sink's display scheduler (pw_sink_gpu_fg_pick): the presented
     * image it was copied from (the address Wine's layer shows), its copy number, and whether the submission that
     * copied it also generated out[slot], the frame halfway from the other slot's to it */
    const void *slot_pixels[2];
    uint64_t slot_frame[2];
    int slot_generated[2];
    /* the generation's whole GPU time (four passes), averaged over the last ones (1/8 each), and how many */
    unsigned gpu_avg_us,gpu_timed;
} fg;
static pthread_mutex_t fg_lock=PTHREAD_MUTEX_INITIALIZER;

#define FG_TRY(call) do { VkResult r_=(call); \
    if(r_!=VK_SUCCESS) {fprintf(stderr,"PWFG failed %s = %d\n",#call,(int)r_);return -1;} } while(0)

static void fg_buffer_free(struct fg_buffer *b)
{
    if(b->buffer) fg_vkDestroyBuffer(device,b->buffer,NULL);
    if(b->memory) fg_vkFreeMemory(device,b->memory,NULL);   /* unmaps it */
    memset(b,0,sizeof(*b));
}
/* a mapped storage buffer: device-local and host-visible if there is such memory (the PS4 has), else
 * host-visible; its GPU address must be its CPU address, as for the sink's image layers (stage 4 hands the
 * outputs to the compositor as image layers). Frees what it made when it fails. */
static int fg_buffer_make(VkDeviceSize bytes,struct fg_buffer *b)
{
    memset(b,0,sizeof(*b));
    VkBufferCreateInfo info={.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=bytes,
                             .usage=VK_BUFFER_USAGE_STORAGE_BUFFER_BIT|VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT};
    VkResult r=vkCreateBuffer(device,&info,NULL,&b->buffer);
    if(r!=VK_SUCCESS) {fprintf(stderr,"PWFG failed vkCreateBuffer %llu = %d\n",(unsigned long long)bytes,(int)r);
                       b->buffer=VK_NULL_HANDLE;return -1;}
    VkMemoryRequirements req;vkGetBufferMemoryRequirements(device,b->buffer,&req);
    uint32_t type=memory_type(req.memoryTypeBits,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT|VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|
                                                 VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if(type==UINT32_MAX) type=memory_type(req.memoryTypeBits,VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if(type==UINT32_MAX) {fprintf(stderr,"PWFG failed no host-visible memory for a buffer\n");fg_buffer_free(b);return -1;}
    VkMemoryAllocateFlagsInfo flags={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_FLAGS_INFO,.flags=VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT};
    VkMemoryAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.pNext=&flags,.allocationSize=req.size,
                                .memoryTypeIndex=type};
    if((r=vkAllocateMemory(device,&alloc,NULL,&b->memory))!=VK_SUCCESS) b->memory=VK_NULL_HANDLE;
    else if((r=vkBindBufferMemory(device,b->buffer,b->memory,0))==VK_SUCCESS) r=vkMapMemory(device,b->memory,0,VK_WHOLE_SIZE,0,&b->data);
    if(r!=VK_SUCCESS) {
        fprintf(stderr,"PWFG failed buffer memory %llu bytes type %u = %d\n",(unsigned long long)req.size,type,(int)r);
        fg_buffer_free(b);return -1;
    }
    VkBufferDeviceAddressInfo address={.sType=VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO,.buffer=b->buffer};
    if(vkGetBufferDeviceAddressKHR(device,&address)!=(uint64_t)(uintptr_t)b->data) {
        fprintf(stderr,"PWFG failed a buffer's GPU address is not its CPU address\n");fg_buffer_free(b);return -1;
    }
    b->bytes=bytes;
    return 0;
}

/* queries: 0,1 around the copy; 2 start of generation, 3 after coarse, 4 after fine, 5 after blend */
static void fg_take_times(int generated)
{
    uint64_t t[FG_QUERIES];
    uint32_t count=generated?FG_QUERIES:2;
    if(!fg.queries || fg_vkGetQueryPoolResults(device,fg.queries,0,count,sizeof(t),t,sizeof(uint64_t),VK_QUERY_RESULT_64_BIT)!=VK_SUCCESS)
        return;
    static const uint32_t from[FG_PASSES]={0,2,3,4};
    uint64_t whole_ns=0;
    for(int pass=0;pass<(generated?FG_PASSES:1);pass++) {
        uint64_t ns=(uint64_t)((double)((t[from[pass]+1]-t[from[pass]])&fg.tick_mask)*fg.tick_ns);
        fg.gpu_sum_ns[pass]+=ns;if(ns>fg.gpu_max_ns[pass]) fg.gpu_max_ns[pass]=ns;++fg.timed[pass];
        whole_ns+=ns;
    }
    if(generated) {  /* stage 4's budget: the copy plus the three generation passes */
        unsigned us=(unsigned)(whole_ns/1000);
        fg.gpu_avg_us=fg.gpu_timed?fg.gpu_avg_us-fg.gpu_avg_us/8+us/8:us;
        ++fg.gpu_timed;
    }
}
/* waits up to timeout_us for fence, as the compositor waits for its own; *waited_us is the time it took */
static VkResult fg_wait_fence(VkFence fence,uint64_t timeout_us,uint64_t *waited_us)
{
    uint64_t start=sceKernelGetProcessTime();
    VkResult r=vkWaitForFences(device,1,&fence,VK_TRUE,timeout_us*1000);
    *waited_us=sceKernelGetProcessTime()-start;
    return r;
}
/* submits cmd alone with fence (the sink's queue is shared with the compositor: queue_lock) */
static VkResult fg_submit(VkCommandBuffer cmd,VkFence fence)
{
    VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&cmd};
    pthread_mutex_lock(&queue_lock);
    VkResult r=vkQueueSubmit(queue,1,&submit,fence);
    pthread_mutex_unlock(&queue_lock);
    return r;
}
static const char *fg_result_word(VkResult r)
{
    return r==VK_SUCCESS?"signalled":r==VK_TIMEOUT?"timeout":r==VK_ERROR_DEVICE_LOST?"device_lost":"error";
}

/* waits for the generation in flight, if any, and takes its GPU times; -1 when the GPU did not finish */
static int fg_wait_done(void)
{
    if(!fg.in_flight) return 0;
    uint64_t waited;
    VkResult r=fg_wait_fence(fg.done,FG_WAIT_US,&waited);
    if(r!=VK_SUCCESS) {
        fprintf(stderr,"PWFG generation wait: fence=%s (%d) waited_us=%llu limit_us=%u\n",fg_result_word(r),(int)r,
                (unsigned long long)waited,(unsigned)FG_WAIT_US);
        return -1;
    }
    vkResetFences(device,1,&fg.done);
    fg.in_flight=0;
    fg_take_times(fg.in_flight_generates);
    return 0;
}

/* everything this file made, in reverse; generation stays off for the run */
static void fg_shutdown(const char *why)
{
    /* a submission still running uses all of it: let it end (or time out) first, and say how that went */
    if(fg.copy_pending || fg.in_flight) {
        uint64_t copy_us=0,generation_us=0;
        VkResult copy=VK_SUCCESS,generation=VK_SUCCESS;
        if(fg.copy_pending) copy=fg_wait_fence(fg.copied,FG_WAIT_US,&copy_us);
        if(fg.in_flight) generation=fg_wait_fence(fg.done,FG_WAIT_US,&generation_us);
        fprintf(stderr,"PWFG shutdown wait: copy=%s waited_us=%llu generation=%s waited_us=%llu\n",
                fg.copy_pending?fg_result_word(copy):"none",(unsigned long long)copy_us,
                fg.in_flight?fg_result_word(generation):"none",(unsigned long long)generation_us);
        if(copy!=VK_SUCCESS || generation!=VK_SUCCESS) {
            /* freeing memory the GPU may still write would fault it (the system kills the app): keep it all */
            memset(&fg,0,sizeof(fg));
            fg.state=-1;
            fprintf(stderr,"PWFG off for this run: %s (a submission is still running: its memory is kept, not freed)\n",why);
            return;
        }
    }
    for(int i=0;i<2;i++) {fg_buffer_free(&fg.color[i]);fg_buffer_free(&fg.luma[i]);fg_buffer_free(&fg.out[i]);}
    fg_buffer_free(&fg.coarse);fg_buffer_free(&fg.fine);
    if(fg_vkDestroyQueryPool && fg.queries) fg_vkDestroyQueryPool(device,fg.queries,NULL);
    if(fg_vkDestroyFence && fg.copied) fg_vkDestroyFence(device,fg.copied,NULL);
    if(fg_vkDestroyFence && fg.done) fg_vkDestroyFence(device,fg.done,NULL);
    if(fg_vkDestroyCommandPool && fg.commands) fg_vkDestroyCommandPool(device,fg.commands,NULL);  /* frees its buffer */
    for(int i=0;i<FG_PASSES;i++) {
        if(fg_vkDestroyPipeline && fg.pipelines[i]) fg_vkDestroyPipeline(device,fg.pipelines[i],NULL);
        if(fg_vkDestroyShaderModule && fg.modules[i]) fg_vkDestroyShaderModule(device,fg.modules[i],NULL);
    }
    if(fg_vkDestroyDescriptorPool && fg.descriptors) fg_vkDestroyDescriptorPool(device,fg.descriptors,NULL);  /* frees the sets */
    if(fg_vkDestroyPipelineLayout && fg.layout) fg_vkDestroyPipelineLayout(device,fg.layout,NULL);
    if(fg_vkDestroyDescriptorSetLayout && fg.set_layout) fg_vkDestroyDescriptorSetLayout(device,fg.set_layout,NULL);
    memset(&fg,0,sizeof(fg));
    fg.state=-1;
    fprintf(stderr,"PWFG off for this run: %s (everything it made is freed)\n",why);
}

/* the pipelines, sync objects and query pool, once; -1 leaves partial objects for fg_shutdown */
static int fg_init(void)
{
#define LOAD(name) fg_##name=(PFN_##name)vk_common_GetDeviceProcAddr(device,#name); \
    if(!fg_##name) {fprintf(stderr,"PWFG failed no %s\n",#name);return -1;}
    FG_FUNCTIONS(LOAD)
#undef LOAD
    const VkPhysicalDeviceLimits *limits=&device_limits;   /* hw_sink_gpu.c device_init */
    if(limits->maxComputeWorkGroupInvocations<64 || limits->maxComputeWorkGroupSize[0]<8 || limits->maxComputeWorkGroupSize[1]<8 ||
       limits->maxPushConstantsSize<sizeof(struct fg_push) || limits->maxStorageBufferRange<(uint64_t)FG_MAX_WIDTH*FG_MAX_HEIGHT*4 ||
       limits->maxPerStageDescriptorStorageBuffers<FG_BINDINGS || limits->maxComputeWorkGroupCount[0]<FG_MAX_WIDTH/8 ||
       limits->maxComputeWorkGroupCount[1]<FG_MAX_HEIGHT/8) {
        fprintf(stderr,"PWFG failed limits: invocations=%u size=%ux%u push=%u storage_range=%u storage_buffers=%u groups=%ux%u\n",
                limits->maxComputeWorkGroupInvocations,limits->maxComputeWorkGroupSize[0],limits->maxComputeWorkGroupSize[1],
                limits->maxPushConstantsSize,limits->maxStorageBufferRange,limits->maxPerStageDescriptorStorageBuffers,
                limits->maxComputeWorkGroupCount[0],limits->maxComputeWorkGroupCount[1]);
        return -1;
    }
    VkDescriptorSetLayoutBinding bindings[FG_BINDINGS];
    for(uint32_t i=0;i<FG_BINDINGS;i++)
        bindings[i]=(VkDescriptorSetLayoutBinding){i,VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1,VK_SHADER_STAGE_COMPUTE_BIT,NULL};
    VkDescriptorSetLayoutCreateInfo set_info={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
                                              .bindingCount=FG_BINDINGS,.pBindings=bindings};
    FG_TRY(vkCreateDescriptorSetLayout(device,&set_info,NULL,&fg.set_layout));
    VkPushConstantRange range={VK_SHADER_STAGE_COMPUTE_BIT,0,sizeof(struct fg_push)};
    VkPipelineLayoutCreateInfo layout_info={.sType=VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,.setLayoutCount=1,
                                            .pSetLayouts=&fg.set_layout,.pushConstantRangeCount=1,.pPushConstantRanges=&range};
    FG_TRY(vkCreatePipelineLayout(device,&layout_info,NULL,&fg.layout));
    static const struct {const uint32_t *code;size_t size;} spirv[FG_PASSES]={
        {fg_capture_comp,sizeof(fg_capture_comp)},{fg_coarse_comp,sizeof(fg_coarse_comp)},
        {fg_fine_comp,sizeof(fg_fine_comp)},{fg_blend_comp,sizeof(fg_blend_comp)}};
    for(int i=0;i<FG_PASSES;i++) {
        VkShaderModuleCreateInfo module={.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,.codeSize=spirv[i].size,
                                         .pCode=spirv[i].code};
        FG_TRY(vkCreateShaderModule(device,&module,NULL,&fg.modules[i]));
        VkComputePipelineCreateInfo info={.sType=VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
            .flags=VK_PIPELINE_CREATE_CAPTURE_INTERNAL_REPRESENTATIONS_BIT_KHR,
            .stage={.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,.stage=VK_SHADER_STAGE_COMPUTE_BIT,
                    .module=fg.modules[i],.pName="main"},.layout=fg.layout};
        FG_TRY(fg_vkCreateComputePipelines(device,VK_NULL_HANDLE,1,&info,NULL,&fg.pipelines[i]));
        /* W153: FLAT instructions hang the PS4's GPU; every pass is checked, not only the one reading by address */
        int flat=uses_flat(fg.pipelines[i],VK_SHADER_STAGE_COMPUTE_BIT);
        if(flat) {fprintf(stderr,"PWFG failed %s: the compiled shader %s\n",fg_pass_names[i],
                          flat>0?"uses FLAT":"could not be checked");return -1;}
    }
    VkDescriptorPoolSize size={VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,2*FG_BINDINGS};
    VkDescriptorPoolCreateInfo pool_info={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,.maxSets=2,
                                          .poolSizeCount=1,.pPoolSizes=&size};
    FG_TRY(vkCreateDescriptorPool(device,&pool_info,NULL,&fg.descriptors));
    VkDescriptorSetLayout set_layouts[2]={fg.set_layout,fg.set_layout};
    VkDescriptorSetAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,.descriptorPool=fg.descriptors,
                                       .descriptorSetCount=2,.pSetLayouts=set_layouts};
    FG_TRY(vkAllocateDescriptorSets(device,&alloc,fg.sets));
    VkCommandPoolCreateInfo command_info={.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                          .flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,.queueFamilyIndex=family};
    FG_TRY(vkCreateCommandPool(device,&command_info,NULL,&fg.commands));
    VkCommandBufferAllocateInfo cmd_info={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=fg.commands,
                                          .level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=2};
    VkCommandBuffer cmds[2];
    FG_TRY(vkAllocateCommandBuffers(device,&cmd_info,cmds));
    fg.copy_cmd=cmds[0];fg.cmd=cmds[1];
    VkFenceCreateInfo fence_info={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    FG_TRY(vkCreateFence(device,&fence_info,NULL,&fg.copied));
    FG_TRY(vkCreateFence(device,&fence_info,NULL,&fg.done));
    if(timestamp_bits && limits->timestampPeriod>0) {
        VkQueryPoolCreateInfo query_info={.sType=VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO,.queryType=VK_QUERY_TYPE_TIMESTAMP,
                                          .queryCount=FG_QUERIES};
        FG_TRY(fg_vkCreateQueryPool(device,&query_info,NULL,&fg.queries));
        fg.tick_ns=limits->timestampPeriod;
        fg.tick_mask=timestamp_bits>=64?UINT64_MAX:(UINT64_C(1)<<timestamp_bits)-1;
    } else fprintf(stderr,"PWFG no GPU timestamps on this queue: times are not measured\n");
    return 0;
}

/* the history, field and output buffers for one frame size; frees the old ones (after the submission in flight) */
static int fg_buffers(unsigned width,unsigned height)
{
    if(fg_wait_done()) return -1;
    for(int i=0;i<2;i++) {fg_buffer_free(&fg.color[i]);fg_buffer_free(&fg.luma[i]);fg_buffer_free(&fg.out[i]);}
    fg_buffer_free(&fg.coarse);fg_buffer_free(&fg.fine);
    fg.width=fg.height=0;
    unsigned luma_w=(width+1)/2,luma_h=(height+1)/2;
    struct fg_push *p=&fg.push;
    p->size[0]=width;p->size[1]=height;p->luma[0]=luma_w;p->luma[1]=luma_h;
    p->coarse[0]=(luma_w+7)/8;p->coarse[1]=(luma_h+7)/8;p->fine[0]=(luma_w+3)/4;p->fine[1]=(luma_h+3)/4;
    VkDeviceSize color=(VkDeviceSize)width*height*4,luma=(VkDeviceSize)luma_w*luma_h*4;
    for(int i=0;i<2;i++)
        if(fg_buffer_make(color,&fg.color[i]) || fg_buffer_make(luma,&fg.luma[i]) || fg_buffer_make(color,&fg.out[i])) return -1;
    if(fg_buffer_make((VkDeviceSize)p->coarse[0]*p->coarse[1]*16,&fg.coarse) ||
       fg_buffer_make((VkDeviceSize)p->fine[0]*p->fine[1]*16,&fg.fine)) return -1;
    for(int s=0;s<2;s++) {
        const struct fg_buffer *bound[FG_BINDINGS]={&fg.color[s],&fg.luma[s],&fg.color[1-s],&fg.luma[1-s],&fg.coarse,&fg.fine,&fg.out[s]};
        VkDescriptorBufferInfo infos[FG_BINDINGS];
        VkWriteDescriptorSet writes[FG_BINDINGS];
        for(int i=0;i<FG_BINDINGS;i++) {
            infos[i]=(VkDescriptorBufferInfo){bound[i]->buffer,0,VK_WHOLE_SIZE};
            writes[i]=(VkWriteDescriptorSet){.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,.dstSet=fg.sets[s],.dstBinding=(uint32_t)i,
                .descriptorCount=1,.descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.pBufferInfo=&infos[i]};
        }
        vkUpdateDescriptorSets(device,FG_BINDINGS,writes,0,NULL);
    }
    fg.width=width;fg.height=height;
    if(fg_trace()) fprintf(stderr,"PWFG buffers %ux%u luma=%ux%u coarse=%ux%u fine=%ux%u bytes=%llu\n",width,height,luma_w,luma_h,
            p->coarse[0],p->coarse[1],p->fine[0],p->fine[1],(unsigned long long)(4*color+2*luma+
            (VkDeviceSize)(p->coarse[0]*p->coarse[1]+p->fine[0]*p->fine[1])*16));
    return 0;
}

static void fg_dispatch(VkCommandBuffer cmd,int pass,VkDescriptorSet set,uint32_t x,uint32_t y)
{
    vkCmdBindPipeline(cmd,VK_PIPELINE_BIND_POINT_COMPUTE,fg.pipelines[pass]);
    vkCmdBindDescriptorSets(cmd,VK_PIPELINE_BIND_POINT_COMPUTE,fg.layout,0,1,&set,0,NULL);
    vkCmdPushConstants(cmd,fg.layout,VK_SHADER_STAGE_COMPUTE_BIT,0,sizeof(fg.push),&fg.push);
    fg_vkCmdDispatch(cmd,(x+7)/8,(y+7)/8,1);
}
static void fg_barrier(VkCommandBuffer cmd)
{
    VkMemoryBarrier barrier={.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER,.srcAccessMask=VK_ACCESS_SHADER_WRITE_BIT,
                             .dstAccessMask=VK_ACCESS_SHADER_READ_BIT};
    fg_vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,0,1,&barrier,0,NULL,0,NULL);
}
static void fg_stamp(VkCommandBuffer cmd,uint32_t query)
{
    if(fg.queries) fg_vkCmdWriteTimestamp(cmd,VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,fg.queries,query);
}

/* Once per run, before the first copy: each primitive the generator relies on, alone in its own submission on
 * fg.copy_cmd, waited for with fg.copied. Logs one line per probe. -1 (generation off) when a submission does not
 * finish; timestamps that cannot be read are dropped (times not measured, stage 4 then never leaves its warm-up);
 * the event is only reported (nothing uses it since 04.19). */
static int fg_probe_run(const char *name,VkResult *submitted,VkResult *fence,uint64_t *waited_us)
{
    *submitted=vkEndCommandBuffer(fg.copy_cmd);
    if(*submitted==VK_SUCCESS) *submitted=fg_submit(fg.copy_cmd,fg.copied);
    *fence=VK_NOT_READY;*waited_us=0;
    if(*submitted==VK_SUCCESS) {
        fg.copy_pending=1;
        *fence=fg_wait_fence(fg.copied,FG_WAIT_US,waited_us);
        if(*fence==VK_SUCCESS) {fg.copy_pending=0;vkResetFences(device,1,&fg.copied);}
    }
    if(*submitted!=VK_SUCCESS || *fence!=VK_SUCCESS) {
        fprintf(stderr,"PWFG probe %s: submit=%d fence=%s (%d) waited_us=%llu limit_us=%u\n",name,(int)*submitted,
                *submitted==VK_SUCCESS?fg_result_word(*fence):"none",(int)*fence,(unsigned long long)*waited_us,
                (unsigned)FG_WAIT_US);
        return -1;
    }
    return 0;
}
static int fg_probe_begin(void)
{
    VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,.flags=VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
    return vkResetCommandBuffer(fg.copy_cmd,0)!=VK_SUCCESS || vkBeginCommandBuffer(fg.copy_cmd,&begin)!=VK_SUCCESS?-1:0;
}
static int fg_probe(void)
{
    VkResult submitted,fence;uint64_t waited;
    /* 1: an empty submission on this file's command buffer and fence */
    if(fg_probe_begin() || fg_probe_run("empty",&submitted,&fence,&waited)) return -1;
    if(fg_trace()) fprintf(stderr,"PWFG probe empty: fence=signalled waited_us=%llu\n",(unsigned long long)waited);
    /* 2: the timestamps (a query pool reset and two writes), read back */
    if(fg.queries) {
        if(fg_probe_begin()) return -1;
        fg_vkCmdResetQueryPool(fg.copy_cmd,fg.queries,0,FG_QUERIES);
        fg_stamp(fg.copy_cmd,0);fg_stamp(fg.copy_cmd,1);
        if(fg_probe_run("timestamps",&submitted,&fence,&waited)) return -1;
        uint64_t t[2]={0,0};
        VkResult r=fg_vkGetQueryPoolResults(device,fg.queries,0,2,sizeof(t),t,sizeof(uint64_t),VK_QUERY_RESULT_64_BIT);
        if(fg_trace()) fprintf(stderr,"PWFG probe timestamps: fence=signalled waited_us=%llu results=%d ticks=%llu\n",(unsigned long long)waited,
                (int)r,r==VK_SUCCESS?(unsigned long long)((t[1]-t[0])&fg.tick_mask):0ull);
        if(r!=VK_SUCCESS) {
            fg_vkDestroyQueryPool(device,fg.queries,NULL);fg.queries=VK_NULL_HANDLE;
            fprintf(stderr,"PWFG timestamps unreadable: times are not measured\n");
        }
    }
    /* 3: what 04.18 waited on: an event the GPU sets after a compute stage, read on the CPU */
    VkEvent event;
    VkEventCreateInfo event_info={.sType=VK_STRUCTURE_TYPE_EVENT_CREATE_INFO};
    VkResult made=fg_vkCreateEvent(device,&event_info,NULL,&event);
    if(made!=VK_SUCCESS) fprintf(stderr,"PWFG probe event: create=%d\n",(int)made);
    else {
        if(fg_probe_begin()) {fg_vkDestroyEvent(device,event,NULL);return -1;}
        fg_vkCmdSetEvent(fg.copy_cmd,event,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
        if(fg_probe_run("event",&submitted,&fence,&waited)) return -1;   /* the event is not freed: it may be in use */
        uint64_t start=sceKernelGetProcessTime(),after=0;
        VkResult status;
        while((status=fg_vkGetEventStatus(device,event))==VK_EVENT_RESET && (after=sceKernelGetProcessTime()-start)<FG_EVENT_POLL_US)
            sched_yield();
        if(fg_trace()) fprintf(stderr,"PWFG probe event: fence=signalled waited_us=%llu event=%s (%d) after_fence_us=%llu\n",
                (unsigned long long)waited,status==VK_EVENT_SET?"set":status==VK_EVENT_RESET?"reset":"error",(int)status,
                (unsigned long long)after);
        fg_vkDestroyEvent(device,event,NULL);
    }
    fprintf(stderr,"PWFG ready: 4 compute passes, FLAT-free, timestamps=%d period_ns=%.3f, copy waits on its fence\n",
            fg.queries!=VK_NULL_HANDLE,fg.tick_ns);
    return 0;
}

static void fg_report(void)
{
    char line[512];int at=0;
    at+=snprintf(line+at,sizeof(line)-at,"PWFG gpu_us");
    for(int i=0;i<FG_PASSES;i++)
        at+=snprintf(line+at,sizeof(line)-at," %s=%llu/%llu",fg_pass_names[i],
                     fg.timed[i]?(unsigned long long)(fg.gpu_sum_ns[i]/fg.timed[i]/1000):0ull,
                     (unsigned long long)(fg.gpu_max_ns[i]/1000));
    fprintf(stderr,"%s (avg/max) present_block_us=%llu/%llu generated=%u frame=%ux%u\n",line,
            fg.blocks?(unsigned long long)(fg.block_sum_us/fg.blocks):0ull,(unsigned long long)fg.block_max_us,fg.generated,
            fg.width,fg.height);
    memset(fg.gpu_sum_ns,0,sizeof(fg.gpu_sum_ns));memset(fg.gpu_max_ns,0,sizeof(fg.gpu_max_ns));memset(fg.timed,0,sizeof(fg.timed));
    fg.block_sum_us=fg.block_max_us=0;fg.blocks=fg.generated=0;
}

/* traces on: the two sources and the generated frame of one generation, as BMPs, once per run */
static void fg_write_bmp(const char *path,const uint32_t *words,unsigned width,unsigned height,int rgba)
{
    FILE *file=fopen(path,"wb");
    if(!file) {fprintf(stderr,"PWFG dump %s failed errno=%d\n",path,errno);return;}
    uint8_t header[54]={'B','M'};
    uint32_t bytes=width*height*4;
    #define PUT32(at,v) do{uint32_t v_=(v);for(int i_=0;i_<4;i_++) header[(at)+i_]=(uint8_t)(v_>>(8*i_));}while(0)
    PUT32(2,54+bytes);PUT32(10,54);PUT32(14,40);PUT32(18,width);PUT32(22,(uint32_t)-(int32_t)height);PUT32(34,bytes);
    #undef PUT32
    header[26]=1;header[28]=32;
    fwrite(header,1,sizeof(header),file);
    static uint32_t row[FG_MAX_WIDTH];
    for(unsigned y=0;y<height;y++) {
        for(unsigned x=0;x<width;x++) {
            uint32_t w=words[(size_t)y*width+x];
            row[x]=(rgba?(w&0xff00ff00u)|((w&0xffu)<<16)|((w>>16)&0xffu):w)|0xff000000u;
        }
        fwrite(row,4,width,file);
    }
    fclose(file);
}
static void fg_dump(int slot)
{
    mkdir("/data/orbisdesk/framegen",0755);
    fg_write_bmp("/data/orbisdesk/framegen/previous.bmp",fg.color[1-slot].data,fg.width,fg.height,(int)fg.push.rgba);
    fg_write_bmp("/data/orbisdesk/framegen/current.bmp",fg.color[slot].data,fg.width,fg.height,(int)fg.push.rgba);
    fg_write_bmp("/data/orbisdesk/framegen/generated.bmp",fg.out[slot].data,fg.width,fg.height,(int)fg.push.rgba);
    fprintf(stderr,"PWFG dump previous/current/generated %ux%u in /data/orbisdesk/framegen\n",fg.width,fg.height);
}

/* one present of a swapchain (pw_wine_sink_ps4.c ft_present, on the presenting thread): 1 a frame was generated,
 * 0 none (another swapchain, no history yet, an unusable image), -1 generation is off for the run.
 * keep: x0,y0,x1,y1 in the image's pixels that the generated frame takes unchanged from this one (stage 5:
 * MangoHud's rectangle), or NULL. restart: the presents before this one were not all copied (generation paused, the
 * program changed), so the history starts again here and nothing is generated against a stale frame */
int pw_sink_gpu_fg_frame(const void *swapchain,const void *pixels,unsigned pitch,unsigned width,unsigned height,int rgba,
                         const int *keep,int restart);
int pw_sink_gpu_fg_frame(const void *swapchain,const void *pixels,unsigned pitch,unsigned width,unsigned height,int rgba,
                         const int *keep,int restart)
{
    int result=0;
    const char *why=NULL;
    uint64_t start=sceKernelGetProcessTime();
    pthread_mutex_lock(&fg_lock);
    if(fg.state<0) {result=-1;goto done;}
    if(!fg.state) {
        if(pool_init() || !images) {why="the sink reads no images by GPU address";goto fail;}
        if(fg_init()) {why="initialisation";goto fail;}
        if(fg_probe()) {why="a probe submission did not finish";goto fail;}
        fg.state=1;
    }
    if(swapchain!=fg.target) {
        if(fg.target && start-fg.target_us<FG_SWITCH_US) goto done;   /* the followed swapchain still presents */
        if(fg_trace()) fprintf(stderr,"PWFG target sc=%p %ux%u (was %p): history restarts\n",swapchain,width,height,fg.target);
        fg.target=swapchain;fg.frames=0;
    }
    fg.target_us=start;
    if(restart && fg.frames) fg.frames=0;
    if(!pixels || pitch%4 || pitch/4<width || width<16 || height<16 || width>FG_MAX_WIDTH || height>FG_MAX_HEIGHT ||
       (uintptr_t)pixels%4) {
        if(fg.refused++<4) fprintf(stderr,"PWFG skipped image %p %ux%u pitch=%u: outside what the generator takes\n",pixels,
                                   width,height,pitch);
        fg.frames=0;goto done;
    }
    /* the last generation read the slot this copy overwrites */
    if(fg_wait_done()) {why="the GPU did not finish a submission";goto fail;}
    if(fg.frames && fg.total_generated==FG_DUMP_AT && !fg.dumped && fg_trace()) {fg.dumped=1;fg_dump((int)((fg.frames-1)&1));}
    if(width!=fg.width || height!=fg.height || (uint32_t)(rgba?1:0)!=fg.push.rgba) {
        if(fg_buffers(width,height)) {why="buffers";goto fail;}
        fg.frames=0;
    }
    int slot=(int)(fg.frames&1),generate=fg.frames>0;
    if(!fg.frames) {memset(fg.slot_pixels,0,sizeof(fg.slot_pixels));memset(fg.slot_generated,0,sizeof(fg.slot_generated));}
    fg.push.source[0]=(uint32_t)(uintptr_t)pixels;fg.push.source[1]=(uint32_t)((uint64_t)(uintptr_t)pixels>>32);
    fg.push.stride=pitch/4;fg.push.rgba=rgba?1:0;
    memset(fg.push.keep,0,sizeof(fg.push.keep));
    if(keep && keep[2]>keep[0] && keep[3]>keep[1]) {
        fg.push.keep[0]=keep[0]>0?(uint32_t)keep[0]:0;fg.push.keep[1]=keep[1]>0?(uint32_t)keep[1]:0;
        fg.push.keep[2]=keep[2]<(int)width?(uint32_t)keep[2]:width;fg.push.keep[3]=keep[3]<(int)height?(uint32_t)keep[3]:height;
    }

    VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,.flags=VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
    /* the copy, alone: the presenting thread waits for its fence (ownership: the copy is complete before this
     * present returns and the game can reuse its image) */
    if(vkResetCommandBuffer(fg.copy_cmd,0)!=VK_SUCCESS || vkBeginCommandBuffer(fg.copy_cmd,&begin)!=VK_SUCCESS) {why="commands";goto fail;}
    if(fg.queries) fg_vkCmdResetQueryPool(fg.copy_cmd,fg.queries,0,FG_QUERIES);
    fg_stamp(fg.copy_cmd,0);
    fg_dispatch(fg.copy_cmd,FG_CAPTURE,fg.sets[slot],fg.push.luma[0],fg.push.luma[1]);
    fg_stamp(fg.copy_cmd,1);
    if(vkEndCommandBuffer(fg.copy_cmd)!=VK_SUCCESS) {why="commands";goto fail;}
    VkResult r=fg_submit(fg.copy_cmd,fg.copied);
    if(r!=VK_SUCCESS) {fprintf(stderr,"PWFG failed copy submit = %d\n",(int)r);why="submit";goto fail;}
    fg.copy_pending=1;
    uint64_t waited;
    r=fg_wait_fence(fg.copied,FG_WAIT_US,&waited);
    if(r!=VK_SUCCESS || (fg.copies<FG_COPY_LOGS && fg_trace()))
        fprintf(stderr,"PWFG copy %llu: fence=%s (%d) waited_us=%llu limit_us=%u image=%p %ux%u pitch=%u\n",
                (unsigned long long)fg.copies,fg_result_word(r),(int)r,(unsigned long long)waited,(unsigned)FG_WAIT_US,
                pixels,width,height,pitch);
    ++fg.copies;
    if(r!=VK_SUCCESS) {why="the GPU did not finish a copy";goto fail;}
    vkResetFences(device,1,&fg.copied);
    fg.copy_pending=0;
    if(!generate) fg_take_times(0);
    else {
        /* the generation: a second submission, not waited for here. Its first barrier orders it after the copy,
         * which is earlier on the same queue. */
        if(vkResetCommandBuffer(fg.cmd,0)!=VK_SUCCESS || vkBeginCommandBuffer(fg.cmd,&begin)!=VK_SUCCESS) {why="commands";goto fail;}
        fg_barrier(fg.cmd);
        fg_stamp(fg.cmd,2);
        fg_dispatch(fg.cmd,FG_COARSE,fg.sets[slot],fg.push.coarse[0],fg.push.coarse[1]);
        fg_stamp(fg.cmd,3);fg_barrier(fg.cmd);
        fg_dispatch(fg.cmd,FG_FINE,fg.sets[slot],fg.push.fine[0],fg.push.fine[1]);
        fg_stamp(fg.cmd,4);fg_barrier(fg.cmd);
        fg_dispatch(fg.cmd,FG_BLEND,fg.sets[slot],width,height);
        fg_stamp(fg.cmd,5);
        if(vkEndCommandBuffer(fg.cmd)!=VK_SUCCESS) {why="commands";goto fail;}
        r=fg_submit(fg.cmd,fg.done);
        if(r!=VK_SUCCESS) {fprintf(stderr,"PWFG failed generation submit = %d\n",(int)r);why="submit";goto fail;}
        fg.in_flight=1;fg.in_flight_generates=1;
    }
    if(generate) {++fg.generated;++fg.total_generated;result=1;}
    fg.slot_pixels[slot]=pixels;fg.slot_frame[slot]=fg.frames;fg.slot_generated[slot]=generate;
    ++fg.frames;
    {
        uint64_t spent=sceKernelGetProcessTime()-start;
        fg.block_sum_us+=spent;if(spent>fg.block_max_us) fg.block_max_us=spent;++fg.blocks;
    }
    if(fg.blocks>=FG_REPORT) {if(fg_trace()) fg_report(); else fg.blocks=0;}
    goto done;
fail:
    fg_shutdown(why?why:"unknown");
    result=-1;
done:
    pthread_mutex_unlock(&fg_lock);
    return result;
}

/* Stage 4 (pw_wine_sink_ps4.c, the presenter thread, sink lock held): the frames to show for the image a layer
 * shows, pixels, as the generator copied it. FG_PICK_READY: *generated is the frame halfway from the previous copy
 * to this one and *real this one's own copy, both width x height words packed in rows of width, in the image's byte
 * order, readable by GPU address like the image itself (fg_buffer_make). The generation may still run: this waits
 * for it up to wait_us. *gpu_us is the generation's averaged GPU time (0 with none measured) and *timed how many
 * generations it averages. Neither buffer is written again before two more copies of the followed swapchain. */
enum {FG_PICK_OFF=-1,FG_PICK_NONE=0,FG_PICK_READY=1,FG_PICK_LATE=2,FG_PICK_FIRST=3};
int pw_sink_gpu_fg_pick(const void *pixels,unsigned width,unsigned height,unsigned wait_us,const void **generated,
                        const void **real,unsigned *gpu_us,unsigned *timed);
int pw_sink_gpu_fg_pick(const void *pixels,unsigned width,unsigned height,unsigned wait_us,const void **generated,
                        const void **real,unsigned *gpu_us,unsigned *timed)
{
    int result=FG_PICK_NONE;
    pthread_mutex_lock(&fg_lock);
    *gpu_us=fg.gpu_avg_us;*timed=fg.gpu_timed;
    if(fg.state<0) {result=FG_PICK_OFF;goto done;}
    if(fg.state!=1 || !fg.frames || width!=fg.width || height!=fg.height) goto done;
    int s=(int)((fg.frames-1)&1);   /* the latest copy */
    if(!pixels || fg.slot_pixels[s]!=pixels || fg.slot_frame[s]!=fg.frames-1) goto done;   /* not the latest */
    if(!fg.slot_generated[s]) {result=FG_PICK_FIRST;goto done;}
    if(fg.in_flight) {   /* the latest submission is this copy's: done when its fence is (not reset here) */
        VkResult r=fg_vkGetFenceStatus(device,fg.done);
        if(r==VK_NOT_READY && wait_us) r=vkWaitForFences(device,1,&fg.done,VK_TRUE,(uint64_t)wait_us*1000);
        if(r!=VK_SUCCESS) {result=FG_PICK_LATE;goto done;}
    }
    *generated=fg.out[s].data;*real=fg.color[s].data;
    result=FG_PICK_READY;
done:
    pthread_mutex_unlock(&fg_lock);
    return result;
}
