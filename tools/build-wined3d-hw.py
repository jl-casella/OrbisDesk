#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware variant of Wine's 32-bit wined3d.dll (PE32).

W160 (phase 6). Same method as build-ddraw-hw.py: the pinned sources are copied to an overlay
and revised there; each object is compiled with the exact command the pinned Wine build uses
(taken from `make -n`), only with the overlay source and a separate output.

Speed for Direct3D 7 games through the Vulkan renderer (SuperMarioKart, W160-W168): cached
staging for uploads and downloads, allocator chunks kept mapped, colour-keyed blits on the GPU and
descriptor sets allocated in batches. W178 removed the timing used to find them (PWCS, PWBLT,
PWUPLOAD, PWDOWNLOAD, the Vulkan call counters).
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
overlay=ROOT/'.deps/wine/wined3d-hw-overlay';work=ROOT/'build/wined3d-hw';out=ROOT/'out/wined3d-hw'
UNITS=('cs','texture_vk')
ARCH='i386-windows'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
shutil.copytree(SOURCE/'dlls/wined3d',overlay)
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
revisions=[]
def revise(path,old,new,why):
    target=overlay/path;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})


# W162: uploads through a staging buffer in CPU-cached memory. W161: each frame SuperMarioKart's
# 800x600 back buffer (system memory, after colour-keyed CPU blits) is uploaded to the swapchain
# texture, ~52 million TSC ticks (~33 ms, ~58 MB/s) for 1.9 MB. The staging buffer asked only for
# HOST_VISIBLE memory, which on the PS4's RADV is memory type 2 (flags 0x6, uncached); types 5
# and 6 (0xe) are cached and coherent, as the presentation pool uses. And each step of the
# large uploads was timed (PWUPLOAD, W162-W177).
revise('texture_vk.c',r'''        if (!wined3d_context_vk_create_bo(context_vk, staging_size,
                VK_BUFFER_USAGE_TRANSFER_SRC_BIT, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT, &staging_bo))
        {
            ERR("Failed to create staging bo.\n");
            return;
        }

        staging_bo_addr.buffer_object = &staging_bo.b;
        staging_bo_addr.addr = NULL;
        if (!(map_ptr = wined3d_context_map_bo_address(context, &staging_bo_addr,
                staging_size, WINED3D_MAP_DISCARD | WINED3D_MAP_WRITE)))
        {
            ERR("Failed to map staging bo.\n");
            wined3d_context_vk_destroy_bo(context_vk, &staging_bo);
            return;
        }

        wined3d_format_copy_data(plane_format, src_bo_addr->addr + src_offset, src_row_pitch, src_slice_pitch,
                map_ptr, staging_row_pitch, staging_slice_pitch, src_width, src_height, src_depth);

        range.offset = 0;
        range.size = staging_size;
        wined3d_context_unmap_bo_address(context, &staging_bo_addr, 1, &range);
''',r'''        /* OrbisDesk W162: cached memory first, uncached as before when there is none */
        if (!wined3d_context_vk_create_bo(context_vk, staging_size, VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT, &staging_bo)
                && !wined3d_context_vk_create_bo(context_vk, staging_size,
                VK_BUFFER_USAGE_TRANSFER_SRC_BIT, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT, &staging_bo))
        {
            ERR("Failed to create staging bo.\n");
            return;
        }

        staging_bo_addr.buffer_object = &staging_bo.b;
        staging_bo_addr.addr = NULL;
        if (!(map_ptr = wined3d_context_map_bo_address(context, &staging_bo_addr,
                staging_size, WINED3D_MAP_DISCARD | WINED3D_MAP_WRITE)))
        {
            ERR("Failed to map staging bo.\n");
            wined3d_context_vk_destroy_bo(context_vk, &staging_bo);
            return;
        }

        wined3d_format_copy_data(plane_format, src_bo_addr->addr + src_offset, src_row_pitch, src_slice_pitch,
                map_ptr, staging_row_pitch, staging_slice_pitch, src_width, src_height, src_depth);

        range.offset = 0;
        range.size = staging_size;
        wined3d_context_unmap_bo_address(context, &staging_bo_addr, 1, &range);
''','Upload staging in cached memory.')

# W163: W162 moved the upload's copy to cached memory (~1 million ticks for 1.9 MB), and showed the
# rest of the cost is mapping the staging buffer: ~31 million ticks (~19 ms) each time. A 32-bit
# wined3d keeps buffer memory mapped only while it maps 128 MB or less in total; past that it unmaps
# after every use, and the next map maps the whole 64 MB allocator chunk again (on the PS4 a placed
# WoW64 mapping, win32u vulkan.c). 512 MB (eight chunks) keeps them mapped and still leaves most of
# a 2 GiB 32-bit address space.
UNITS=UNITS+('adapter_vk','context_vk')
# W229: swapchain.c, the Vulkan swapchain follows the window ddraw gives it (SetClipper)
UNITS=UNITS+('swapchain',)
# W178: descriptor sets in batches. W165-W167 (SuperMarioKart): ~185 vkAllocateDescriptorSets a
# frame, one per draw. In a 32-bit program each is a 32->64-bit crossing that the Vulkan call batching
# cannot defer, since it returns the set. Sets now come 16 at a time per layout from the current
# pool; the spares wait in a small cache keyed by pool and layout, which forgets a pool when it is
# reset, retired or destroyed (its spares go with it). A batch that does not fit falls back to
# wined3d's own single allocation, which retires the full pool as before. Only the command stream
# thread allocates descriptor sets.
revise('context_vk.c','''static void wined3d_context_vk_return_vk_descriptor_pool(struct wined3d_context_vk *context_vk,
        VkDescriptorPool vk_descriptor_pool)
{''','''/* OrbisDesk W178: spare descriptor sets (tools/build-wined3d-hw.py) */
#define PW_DESC_BATCH 16
static struct
{
    VkDescriptorPool pool;
    VkDescriptorSetLayout layout;
    unsigned int count;
    VkDescriptorSet sets[PW_DESC_BATCH];
} pw_desc_cache[8];
static unsigned int pw_desc_next;

static void pw_desc_forget_pool(VkDescriptorPool vk_descriptor_pool)
{
    unsigned int i;

    for (i = 0; i < ARRAY_SIZE(pw_desc_cache); ++i)
    {
        if (pw_desc_cache[i].pool != vk_descriptor_pool) continue;
        pw_desc_cache[i].pool = VK_NULL_HANDLE;
        pw_desc_cache[i].count = 0;
    }
}

static void wined3d_context_vk_return_vk_descriptor_pool(struct wined3d_context_vk *context_vk,
        VkDescriptorPool vk_descriptor_pool)
{''','Spare descriptor sets, per pool and layout.')
revise('context_vk.c','''    const struct wined3d_vk_info *vk_info = context_vk->vk_info;

    if (!wined3d_array_reserve((void **)&context_vk->vk_descriptor_pools, &context_vk->vk_descriptor_pools_size,
            context_vk->vk_descriptor_pool_count + 1, sizeof(*context_vk->vk_descriptor_pools)))''','''    const struct wined3d_vk_info *vk_info = context_vk->vk_info;

    pw_desc_forget_pool(vk_descriptor_pool);
    if (!wined3d_array_reserve((void **)&context_vk->vk_descriptor_pools, &context_vk->vk_descriptor_pools_size,
            context_vk->vk_descriptor_pool_count + 1, sizeof(*context_vk->vk_descriptor_pools)))''',
       'A pool returned for reuse has no spares.')
revise('context_vk.c','''    struct wined3d_retired_object_vk *o;

    if (context_vk->completed_command_buffer_id >= command_buffer_id)
    {
        wined3d_context_vk_return_vk_descriptor_pool(context_vk, vk_descriptor_pool);''','''    struct wined3d_retired_object_vk *o;

    pw_desc_forget_pool(vk_descriptor_pool);
    if (context_vk->completed_command_buffer_id >= command_buffer_id)
    {
        wined3d_context_vk_return_vk_descriptor_pool(context_vk, vk_descriptor_pool);''',
       'A retired pool has no spares.')
revise('context_vk.c','''    for (i = 0; i < context_vk->vk_descriptor_pool_count; ++i)
        VK_CALL(vkDestroyDescriptorPool(device_vk->vk_device, context_vk->vk_descriptor_pools[i], NULL));''','''    memset(pw_desc_cache, 0, sizeof(pw_desc_cache));
    for (i = 0; i < context_vk->vk_descriptor_pool_count; ++i)
        VK_CALL(vkDestroyDescriptorPool(device_vk->vk_device, context_vk->vk_descriptor_pools[i], NULL));''',
       'Destroyed pools have no spares.')
revise('context_vk.c','''    set_desc.pSetLayouts = &vk_set_layout;
    if ((vr = VK_CALL(vkAllocateDescriptorSets(device_vk->vk_device, &set_desc, &vk_descriptor_set))) >= 0)
        return vk_descriptor_set;
''','''    set_desc.pSetLayouts = &vk_set_layout;

    /* OrbisDesk W178: a spare from this pool first, then a batch of PW_DESC_BATCH */
    {
        VkDescriptorSetLayout layouts[PW_DESC_BATCH];
        VkDescriptorSet sets[PW_DESC_BATCH];
        struct VkDescriptorSetAllocateInfo batch_desc = set_desc;
        unsigned int i, slot = ARRAY_SIZE(pw_desc_cache);

        for (i = 0; i < ARRAY_SIZE(pw_desc_cache); ++i)
        {
            if (pw_desc_cache[i].pool != vk_descriptor_pool || pw_desc_cache[i].layout != vk_set_layout) continue;
            if (pw_desc_cache[i].count) return pw_desc_cache[i].sets[--pw_desc_cache[i].count];
            slot = i;
        }
        for (i = 0; i < PW_DESC_BATCH; ++i) layouts[i] = vk_set_layout;
        batch_desc.descriptorSetCount = PW_DESC_BATCH;
        batch_desc.pSetLayouts = layouts;
        if (VK_CALL(vkAllocateDescriptorSets(device_vk->vk_device, &batch_desc, sets)) >= 0)
        {
            /* another layout's spares, if their entry is taken over, stay allocated in their
             * pool until it is reset */
            if (slot == ARRAY_SIZE(pw_desc_cache)) slot = pw_desc_next++ % ARRAY_SIZE(pw_desc_cache);
            pw_desc_cache[slot].pool = vk_descriptor_pool;
            pw_desc_cache[slot].layout = vk_set_layout;
            pw_desc_cache[slot].count = PW_DESC_BATCH - 1;
            memcpy(pw_desc_cache[slot].sets, sets + 1, (PW_DESC_BATCH - 1) * sizeof(*sets));
            return sets[0];
        }
    }

    if ((vr = VK_CALL(vkAllocateDescriptorSets(device_vk->vk_device, &set_desc, &vk_descriptor_set))) >= 0)
        return vk_descriptor_set;
''','Descriptor sets in batches of 16.')
# W164: downloads too. W163: with uploads fixed (~1.35 million ticks for 800x600), a colour-keyed
# sprite blit onto a back buffer the GPU has just drawn costs ~70 million ticks (~44 ms): the CPU
# blitter first downloads the whole back buffer, through a staging buffer asked only as
# HOST_VISIBLE (uncached on the PS4), and reads it back on the CPU. Cached memory first, as for
# uploads (each step of large downloads was timed, PWDOWNLOAD, W164-W177).
revise('texture_vk.c',r'''        if (!wined3d_context_vk_create_bo(context_vk, sub_resource->size,
                VK_BUFFER_USAGE_TRANSFER_DST_BIT, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT, &staging_bo))
        {
            ERR("Failed to create staging bo.\n");
            return;
        }''',r'''        /* OrbisDesk W164: cached memory first, uncached as before when there is none */
        if (!wined3d_context_vk_create_bo(context_vk, sub_resource->size, VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT, &staging_bo)
                && !wined3d_context_vk_create_bo(context_vk, sub_resource->size,
                VK_BUFFER_USAGE_TRANSFER_DST_BIT, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT, &staging_bo))
        {
            ERR("Failed to create staging bo.\n");
            return;
        }''','Download staging in cached memory.')
revise('adapter_vk.c','''    if (device_vk->d.adapter->mapped_size <= MAX_PERSISTENT_MAPPED_BYTES)''',
       '''    /* OrbisDesk W163: 512 MB here instead of MAX_PERSISTENT_MAPPED_BYTES (128 MB on 32-bit) */
    if (device_vk->d.adapter->mapped_size <= (sizeof(void *) >= 8 ? MAX_PERSISTENT_MAPPED_BYTES : 512 * 1024 * 1024))''',
       'Keep allocator chunks mapped up to 512 MB in 32-bit processes.')

# W168: the GPU colour-keyed blits below keep their sampled source image, its view and descriptor
# set between blits, and the destination's view and framebuffer within a command buffer: W167 showed
# ~7 images, ~14 views and a framebuffer per sprite made and freed every frame.
# W166: colour-keyed blits on the GPU. W164 (SuperMarioKart, ~36 fps): the HUD sprites are
# DirectDraw blits with a source colour key (SRC_CKEY_OVERRIDE), which wined3d's Vulkan blitter does
# not take; the CPU blitter then downloads the whole back buffer the GPU has just drawn (~0.65 ms of
# copy plus a wait for the GPU), blits on the CPU and uploads it again (~0.85 ms), every frame. Here
# vk_blitter_blit draws them: the source rectangle is copied into a sampled image and drawn over the
# destination with a fragment shader that discards key-coloured texels. Only for 32-bit BGRA/BGRX
# 2D textures into a render target; anything else goes to the next blitter as before.
import os
glslang=pathlib.Path(os.path.expanduser('~/vk-h0/host-tools/bin/glslang'))
(work/'pw_ckey.vert').write_text('''#version 450
layout(push_constant) uniform Push { vec4 src; uvec4 key; } p;
layout(location = 0) out vec2 uv;
void main()
{
    vec2 corner = vec2(gl_VertexIndex & 1, gl_VertexIndex >> 1);
    uv = mix(p.src.xy, p.src.zw, corner);
    gl_Position = vec4(corner * 2.0 - 1.0, 0.0, 1.0);
}
''')
(work/'pw_ckey.frag').write_text('''#version 450
layout(set = 0, binding = 0) uniform texture2D image;
layout(set = 0, binding = 1) uniform sampler point;
layout(push_constant) uniform Push { vec4 src; uvec4 key; } p;
layout(location = 0) in vec2 uv;
layout(location = 0) out vec4 color;
/* the key is a range of 0x00RRGGBB values, compared per channel as DirectDraw does */
void main()
{
    vec4 texel = texture(sampler2D(image, point), uv);
    uvec3 v = uvec3(round(texel.rgb * 255.0));
    uvec3 low = uvec3((p.key.x >> 16) & 0xffu, (p.key.x >> 8) & 0xffu, p.key.x & 0xffu);
    uvec3 high = uvec3((p.key.y >> 16) & 0xffu, (p.key.y >> 8) & 0xffu, p.key.y & 0xffu);
    if (all(greaterThanEqual(v, low)) && all(lessThanEqual(v, high))) discard;
    color = texel;
}
''')
for stage in ('vert','frag'):
    subprocess.run([str(glslang),'-V','--target-env','vulkan1.0','--vn','pw_ckey_'+stage,'-o',
                    str(overlay/('pw_ckey_'+stage+'.h')),str(work/('pw_ckey.'+stage))],check=True,capture_output=True)
revise('texture_vk.c',r'''static DWORD vk_blitter_blit(struct wined3d_blitter *blitter, enum wined3d_blit_op op,''',r'''/* OrbisDesk W166: colour-keyed blits drawn on the GPU (tools/build-wined3d-hw.py) */
#include "pw_ckey_vert.h"
#include "pw_ckey_frag.h"

static struct
{
    VkDevice vk_device;
    VkSampler vk_sampler;
    VkDescriptorSetLayout vk_set_layout;
    VkPipelineLayout vk_pipeline_layout;
    VkShaderModule vk_vs, vk_fs;
    VkFormat vk_format;
    VkRenderPass vk_render_pass;
    VkPipeline vk_pipeline;
    unsigned int blits;
    /* W168: kept between blits. The sampled copy of the source: one image that grows to the
     * largest rectangle seen, its view and a descriptor set from a pool of this path's own. */
    VkDescriptorPool vk_pool;
    struct wined3d_image_vk tmp;
    VkImageView tmp_view;
    VkFormat tmp_format;
    unsigned int tmp_width, tmp_height;
    bool tmp_read;          /* a draw has read it: SHADER_READ_ONLY, else UNDEFINED */
    VkDescriptorSet vk_set;
    /* the destination's view and framebuffer, for the blits of one command buffer into the
     * same image: the image cannot go away while that command buffer records */
    uint64_t fb_command_buffer_id;
    VkImage fb_image;
    unsigned int fb_level, fb_layer, fb_width, fb_height;
    VkImageView fb_view;
    VkFramebuffer vk_framebuffer;
    unsigned int images, framebuffers;
} pw_ckey;

static bool pw_ckey_init(struct wined3d_context_vk *context_vk, VkFormat vk_format)
{
    struct wined3d_device_vk *device_vk = wined3d_device_vk(context_vk->c.device);
    const struct wined3d_vk_info *vk_info = context_vk->vk_info;
    VkDevice vk_device = device_vk->vk_device;

    if (pw_ckey.vk_device != vk_device)
    {
        memset(&pw_ckey, 0, sizeof(pw_ckey));
        pw_ckey.vk_device = vk_device;
    }
    if (!pw_ckey.vk_sampler)
    {
        VkSamplerCreateInfo info = {VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
        info.magFilter = info.minFilter = VK_FILTER_NEAREST;
        info.mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST;
        info.addressModeU = info.addressModeV = info.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
        if (VK_CALL(vkCreateSampler(vk_device, &info, NULL, &pw_ckey.vk_sampler)) < 0) return false;
    }
    if (!pw_ckey.vk_set_layout)
    {
        VkDescriptorSetLayoutBinding bindings[2] =
        {
            {0, VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, 1, VK_SHADER_STAGE_FRAGMENT_BIT, NULL},
            {1, VK_DESCRIPTOR_TYPE_SAMPLER, 1, VK_SHADER_STAGE_FRAGMENT_BIT, NULL},
        };
        VkDescriptorSetLayoutCreateInfo info = {VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        info.bindingCount = 2;
        info.pBindings = bindings;
        if (VK_CALL(vkCreateDescriptorSetLayout(vk_device, &info, NULL, &pw_ckey.vk_set_layout)) < 0) return false;
    }
    if (!pw_ckey.vk_pipeline_layout)
    {
        VkPushConstantRange range = {VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT, 0, 32};
        VkPipelineLayoutCreateInfo info = {VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        info.setLayoutCount = 1;
        info.pSetLayouts = &pw_ckey.vk_set_layout;
        info.pushConstantRangeCount = 1;
        info.pPushConstantRanges = &range;
        if (VK_CALL(vkCreatePipelineLayout(vk_device, &info, NULL, &pw_ckey.vk_pipeline_layout)) < 0) return false;
    }
    if (!pw_ckey.vk_vs)
    {
        VkShaderModuleCreateInfo info = {VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        info.codeSize = sizeof(pw_ckey_vert);
        info.pCode = pw_ckey_vert;
        if (VK_CALL(vkCreateShaderModule(vk_device, &info, NULL, &pw_ckey.vk_vs)) < 0) return false;
        info.codeSize = sizeof(pw_ckey_frag);
        info.pCode = pw_ckey_frag;
        if (VK_CALL(vkCreateShaderModule(vk_device, &info, NULL, &pw_ckey.vk_fs)) < 0) return false;
    }
    if (pw_ckey.vk_format != vk_format || !pw_ckey.vk_pipeline)
    {
        VkAttachmentDescription attachment = {0, vk_format, VK_SAMPLE_COUNT_1_BIT, VK_ATTACHMENT_LOAD_OP_LOAD,
                VK_ATTACHMENT_STORE_OP_STORE, VK_ATTACHMENT_LOAD_OP_DONT_CARE, VK_ATTACHMENT_STORE_OP_DONT_CARE,
                VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
        VkAttachmentReference reference = {0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
        VkSubpassDescription subpass = {0, VK_PIPELINE_BIND_POINT_GRAPHICS};
        VkRenderPassCreateInfo pass_info = {VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};
        VkPipelineShaderStageCreateInfo stages[2] = {{VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO},
                {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO}};
        VkPipelineVertexInputStateCreateInfo vertex = {VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
        VkPipelineInputAssemblyStateCreateInfo assembly = {VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
        VkPipelineViewportStateCreateInfo viewport = {VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
        VkPipelineRasterizationStateCreateInfo raster = {VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
        VkPipelineMultisampleStateCreateInfo multisample = {VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
        VkPipelineColorBlendAttachmentState blend_attachment = {0};
        VkPipelineColorBlendStateCreateInfo blend = {VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
        static const VkDynamicState dynamic_states[] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
        VkPipelineDynamicStateCreateInfo dynamic = {VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};
        VkGraphicsPipelineCreateInfo info = {VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};

        subpass.colorAttachmentCount = 1;
        subpass.pColorAttachments = &reference;
        pass_info.attachmentCount = 1;
        pass_info.pAttachments = &attachment;
        pass_info.subpassCount = 1;
        pass_info.pSubpasses = &subpass;
        if (VK_CALL(vkCreateRenderPass(vk_device, &pass_info, NULL, &pw_ckey.vk_render_pass)) < 0) return false;

        stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
        stages[0].module = pw_ckey.vk_vs;
        stages[0].pName = "main";
        stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
        stages[1].module = pw_ckey.vk_fs;
        stages[1].pName = "main";
        assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP;
        viewport.viewportCount = 1;
        viewport.scissorCount = 1;
        raster.polygonMode = VK_POLYGON_MODE_FILL;
        raster.cullMode = VK_CULL_MODE_NONE;
        raster.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE;
        raster.lineWidth = 1.0f;
        multisample.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
        blend_attachment.colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT
                | VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT;
        blend.attachmentCount = 1;
        blend.pAttachments = &blend_attachment;
        dynamic.dynamicStateCount = 2;
        dynamic.pDynamicStates = dynamic_states;
        info.stageCount = 2;
        info.pStages = stages;
        info.pVertexInputState = &vertex;
        info.pInputAssemblyState = &assembly;
        info.pViewportState = &viewport;
        info.pRasterizationState = &raster;
        info.pMultisampleState = &multisample;
        info.pColorBlendState = &blend;
        info.pDynamicState = &dynamic;
        info.layout = pw_ckey.vk_pipeline_layout;
        info.renderPass = pw_ckey.vk_render_pass;
        if (VK_CALL(vkCreateGraphicsPipelines(vk_device, VK_NULL_HANDLE, 1, &info, NULL, &pw_ckey.vk_pipeline)) < 0)
            return false;
        pw_ckey.vk_format = vk_format;
        TRACE("PWCKEY GPU colour-keyed blits for format %u.\n", vk_format);
    }
    return true;
}

static bool pw_ckey_format(enum wined3d_format_id id)
{
    return id == WINED3DFMT_B8G8R8X8_UNORM || id == WINED3DFMT_B8G8R8A8_UNORM;
}

/* W168: the sampled copy of the source, grown when a larger rectangle comes; its descriptor set
 * is allocated once per image from this path's own pool (sets in use are never updated). */
static bool pw_ckey_tmp(struct wined3d_context_vk *context_vk, VkFormat vk_format, unsigned int width, unsigned int height)
{
    struct wined3d_device_vk *device_vk = wined3d_device_vk(context_vk->c.device);
    const struct wined3d_vk_info *vk_info = context_vk->vk_info;
    VkImageViewCreateInfo view_info = {VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
    VkDescriptorSetAllocateInfo set_info = {VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    VkDescriptorImageInfo image_info = {0}, sampler_info = {0};
    VkWriteDescriptorSet writes[2] = {{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET}, {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET}};
    VkImageCreateInfo image_desc;
    struct wined3d_image_vk image;
    VkImageView view;
    VkDescriptorSet set;
    unsigned int w, h;

    if (pw_ckey.tmp.vk_image && pw_ckey.tmp_format == vk_format && width <= pw_ckey.tmp_width && height <= pw_ckey.tmp_height)
        return true;
    if (!pw_ckey.vk_pool)
    {
        static const VkDescriptorPoolSize sizes[] = {{VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, 64}, {VK_DESCRIPTOR_TYPE_SAMPLER, 64}};
        VkDescriptorPoolCreateInfo pool_info = {VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
        pool_info.maxSets = 64;
        pool_info.poolSizeCount = 2;
        pool_info.pPoolSizes = sizes;
        if (VK_CALL(vkCreateDescriptorPool(device_vk->vk_device, &pool_info, NULL, &pw_ckey.vk_pool)) < 0) return false;
    }
    w = max(width, pw_ckey.tmp_format == vk_format ? pw_ckey.tmp_width : 0);
    h = max(height, pw_ckey.tmp_format == vk_format ? pw_ckey.tmp_height : 0);
    w = (w + 63) & ~63u;
    h = (h + 63) & ~63u;
    wined3d_init_vk_image_info(&image_desc, VK_IMAGE_TYPE_2D, VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT,
            vk_format, w, h, 1);
    if (!wined3d_context_vk_create_image(context_vk, &image_desc, &image)) return false;
    view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
    view_info.image = image.vk_image;
    view_info.format = vk_format;
    view_info.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    view_info.subresourceRange.levelCount = 1;
    view_info.subresourceRange.layerCount = 1;
    if (VK_CALL(vkCreateImageView(device_vk->vk_device, &view_info, NULL, &view)) < 0)
    {
        wined3d_context_vk_destroy_image(context_vk, &image);
        return false;
    }
    set_info.descriptorPool = pw_ckey.vk_pool;
    set_info.descriptorSetCount = 1;
    set_info.pSetLayouts = &pw_ckey.vk_set_layout;
    if (VK_CALL(vkAllocateDescriptorSets(device_vk->vk_device, &set_info, &set)) < 0)
    {
        /* a full pool (64 growths) starts again; sets of the old pool may still be in use */
        ERR("PWCKEY descriptor pool full; the blit goes to the CPU.\n");
        wined3d_context_vk_destroy_vk_image_view(context_vk, view, context_vk->current_command_buffer.id);
        wined3d_context_vk_destroy_image(context_vk, &image);
        return false;
    }
    image_info.imageView = view;
    image_info.imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    sampler_info.sampler = pw_ckey.vk_sampler;
    writes[0].dstSet = writes[1].dstSet = set;
    writes[0].dstBinding = 0;
    writes[0].descriptorCount = 1;
    writes[0].descriptorType = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE;
    writes[0].pImageInfo = &image_info;
    writes[1].dstBinding = 1;
    writes[1].descriptorCount = 1;
    writes[1].descriptorType = VK_DESCRIPTOR_TYPE_SAMPLER;
    writes[1].pImageInfo = &sampler_info;
    VK_CALL(vkUpdateDescriptorSets(device_vk->vk_device, 2, writes, 0, NULL));

    if (pw_ckey.tmp.vk_image)
    {
        /* freed once the command buffers that drew with it are done */
        wined3d_context_vk_destroy_vk_image_view(context_vk, pw_ckey.tmp_view, context_vk->current_command_buffer.id);
        wined3d_context_vk_reference_image(context_vk, &pw_ckey.tmp);
        wined3d_context_vk_destroy_image(context_vk, &pw_ckey.tmp);
    }
    pw_ckey.tmp = image;
    pw_ckey.tmp_view = view;
    pw_ckey.tmp_format = vk_format;
    pw_ckey.tmp_width = w;
    pw_ckey.tmp_height = h;
    pw_ckey.tmp_read = false;
    pw_ckey.vk_set = set;
    ++pw_ckey.images;
    return true;
}

/* W168: the destination's view and framebuffer, reused while the command buffer and the image
 * stay the same */
static bool pw_ckey_framebuffer(struct wined3d_context_vk *context_vk, struct wined3d_texture_vk *dst_texture_vk,
        const VkImageSubresourceRange *dst_range, unsigned int dst_width, unsigned int dst_height, VkFormat vk_format)
{
    struct wined3d_device_vk *device_vk = wined3d_device_vk(context_vk->c.device);
    const struct wined3d_vk_info *vk_info = context_vk->vk_info;
    VkImageViewCreateInfo view_info = {VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
    VkFramebufferCreateInfo fb_info = {VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
    uint64_t id = context_vk->current_command_buffer.id;
    VkImageView view;
    VkFramebuffer framebuffer;

    if (pw_ckey.vk_framebuffer && pw_ckey.fb_command_buffer_id == id && pw_ckey.fb_image == dst_texture_vk->image.vk_image
            && pw_ckey.fb_level == dst_range->baseMipLevel && pw_ckey.fb_layer == dst_range->baseArrayLayer
            && pw_ckey.fb_width == dst_width && pw_ckey.fb_height == dst_height)
        return true;
    view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
    view_info.image = dst_texture_vk->image.vk_image;
    view_info.format = vk_format;
    view_info.subresourceRange = *dst_range;
    if (VK_CALL(vkCreateImageView(device_vk->vk_device, &view_info, NULL, &view)) < 0) return false;
    fb_info.renderPass = pw_ckey.vk_render_pass;
    fb_info.attachmentCount = 1;
    fb_info.pAttachments = &view;
    fb_info.width = dst_width;
    fb_info.height = dst_height;
    fb_info.layers = 1;
    if (VK_CALL(vkCreateFramebuffer(device_vk->vk_device, &fb_info, NULL, &framebuffer)) < 0)
    {
        wined3d_context_vk_destroy_vk_image_view(context_vk, view, id);
        return false;
    }
    if (pw_ckey.vk_framebuffer)
    {
        /* used by the command buffer it was made for, or an earlier one */
        wined3d_context_vk_destroy_vk_framebuffer(context_vk, pw_ckey.vk_framebuffer, pw_ckey.fb_command_buffer_id);
        wined3d_context_vk_destroy_vk_image_view(context_vk, pw_ckey.fb_view, pw_ckey.fb_command_buffer_id);
    }
    pw_ckey.vk_framebuffer = framebuffer;
    pw_ckey.fb_view = view;
    pw_ckey.fb_command_buffer_id = id;
    pw_ckey.fb_image = dst_texture_vk->image.vk_image;
    pw_ckey.fb_level = dst_range->baseMipLevel;
    pw_ckey.fb_layer = dst_range->baseArrayLayer;
    pw_ckey.fb_width = dst_width;
    pw_ckey.fb_height = dst_height;
    ++pw_ckey.framebuffers;
    return true;
}

static bool pw_ckey_blit(struct wined3d_context_vk *context_vk, struct wined3d_texture *src_texture,
        unsigned int src_sub_resource_idx, const RECT *src_rect, struct wined3d_texture *dst_texture,
        unsigned int dst_sub_resource_idx, const RECT *dst_rect, const struct wined3d_color_key *colour_key)
{
    struct wined3d_texture_vk *src_texture_vk = wined3d_texture_vk(src_texture);
    struct wined3d_texture_vk *dst_texture_vk = wined3d_texture_vk(dst_texture);
    const struct wined3d_vk_info *vk_info = context_vk->vk_info;
    const struct wined3d_format_vk *src_format_vk = wined3d_format_vk(src_texture->resource.format);
    const struct wined3d_format_vk *dst_format_vk = wined3d_format_vk(dst_texture->resource.format);
    unsigned int width = src_rect->right - src_rect->left, height = src_rect->bottom - src_rect->top;
    unsigned int dst_level = dst_sub_resource_idx % dst_texture->level_count;
    unsigned int dst_width = wined3d_texture_get_level_width(dst_texture, dst_level);
    unsigned int dst_height = wined3d_texture_get_level_height(dst_texture, dst_level);
    VkImageSubresourceRange src_range, dst_range, tmp_range = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    VkImageLayout src_layout;
    VkCommandBuffer vk_command_buffer;
    VkRenderPassBeginInfo begin = {VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
    VkImageCopy region;
    VkViewport vk_viewport;
    VkRect2D scissor;
    struct { float src[4]; uint32_t key[4]; } push = {{0.0f, 0.0f, 1.0f, 1.0f}, {0}};
    LONG left = max(dst_rect->left, 0), top = max(dst_rect->top, 0);
    LONG right = min(dst_rect->right, (LONG)dst_width), bottom = min(dst_rect->bottom, (LONG)dst_height);

    if (!pw_ckey_format(src_texture->resource.format->id) || !pw_ckey_format(dst_texture->resource.format->id)
            || src_texture->resource.type != WINED3D_RTYPE_TEXTURE_2D
            || dst_texture->resource.type != WINED3D_RTYPE_TEXTURE_2D
            || wined3d_resource_get_sample_count(&src_texture->resource) > 1
            || wined3d_resource_get_sample_count(&dst_texture->resource) > 1
            || !(dst_texture->resource.bind_flags & WINED3D_BIND_RENDER_TARGET)
            || !(src_texture->resource.access & WINED3D_RESOURCE_ACCESS_GPU)
            || !width || !height || left >= right || top >= bottom)
        return false;
    if (!pw_ckey_init(context_vk, dst_format_vk->vk_format))
    {
        ERR("PWCKEY setup failed; colour-keyed blits stay on the CPU.\n");
        return false;
    }

    if (!wined3d_texture_load_location(src_texture, src_sub_resource_idx, &context_vk->c, WINED3D_LOCATION_TEXTURE_RGB))
        return false;
    if (wined3d_texture_is_full_rect(dst_texture, dst_level, dst_rect))
    {
        if (!wined3d_texture_prepare_location(dst_texture, dst_sub_resource_idx, &context_vk->c, WINED3D_LOCATION_TEXTURE_RGB))
            return false;
    }
    else if (!wined3d_texture_load_location(dst_texture, dst_sub_resource_idx, &context_vk->c, WINED3D_LOCATION_TEXTURE_RGB))
        return false;
    if (!(vk_command_buffer = wined3d_context_vk_get_command_buffer(context_vk)))
        return false;
    wined3d_context_vk_end_current_render_pass(context_vk);

    src_range.aspectMask = dst_range.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    src_range.baseMipLevel = src_sub_resource_idx % src_texture->level_count;
    src_range.baseArrayLayer = src_sub_resource_idx / src_texture->level_count;
    dst_range.baseMipLevel = dst_level;
    dst_range.baseArrayLayer = dst_sub_resource_idx / dst_texture->level_count;
    src_range.levelCount = src_range.layerCount = dst_range.levelCount = dst_range.layerCount = 1;
    if (!pw_ckey_tmp(context_vk, src_format_vk->vk_format, width, height)
            || !pw_ckey_framebuffer(context_vk, dst_texture_vk, &dst_range, dst_width, dst_height, dst_format_vk->vk_format))
        return false;
    src_layout = src_texture_vk->layout == VK_IMAGE_LAYOUT_GENERAL ? VK_IMAGE_LAYOUT_GENERAL
            : VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;

    /* the source rectangle into the corner of the sampled image, after the last draw that read it */
    wined3d_context_vk_image_barrier(context_vk, vk_command_buffer,
            VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
            vk_access_mask_from_bind_flags(src_texture->resource.bind_flags), VK_ACCESS_TRANSFER_READ_BIT,
            src_texture_vk->layout, src_layout, src_texture_vk->image.vk_image, &src_range);
    wined3d_context_vk_image_barrier(context_vk, vk_command_buffer,
            pw_ckey.tmp_read ? VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT : VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, pw_ckey.tmp_read ? VK_ACCESS_SHADER_READ_BIT : 0, VK_ACCESS_TRANSFER_WRITE_BIT,
            pw_ckey.tmp_read ? VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL : VK_IMAGE_LAYOUT_UNDEFINED,
            VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, pw_ckey.tmp.vk_image, &tmp_range);
    memset(&region, 0, sizeof(region));
    region.srcSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    region.srcSubresource.mipLevel = src_range.baseMipLevel;
    region.srcSubresource.baseArrayLayer = src_range.baseArrayLayer;
    region.srcSubresource.layerCount = 1;
    region.srcOffset.x = src_rect->left;
    region.srcOffset.y = src_rect->top;
    region.dstSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    region.dstSubresource.layerCount = 1;
    region.extent.width = width;
    region.extent.height = height;
    region.extent.depth = 1;
    VK_CALL(vkCmdCopyImage(vk_command_buffer, src_texture_vk->image.vk_image, src_layout,
            pw_ckey.tmp.vk_image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region));
    wined3d_context_vk_image_barrier(context_vk, vk_command_buffer,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,
            VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT,
            VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, pw_ckey.tmp.vk_image, &tmp_range);
    wined3d_context_vk_image_barrier(context_vk, vk_command_buffer,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
            VK_ACCESS_TRANSFER_READ_BIT, vk_access_mask_from_bind_flags(src_texture->resource.bind_flags),
            src_layout, src_texture_vk->layout, src_texture_vk->image.vk_image, &src_range);
    pw_ckey.tmp_read = true;

    /* the sprite over the destination */
    wined3d_context_vk_image_barrier(context_vk, vk_command_buffer,
            VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
            vk_access_mask_from_bind_flags(dst_texture->resource.bind_flags),
            VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
            dst_texture_vk->layout, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, dst_texture_vk->image.vk_image, &dst_range);
    scissor.offset.x = left;
    scissor.offset.y = top;
    scissor.extent.width = right - left;
    scissor.extent.height = bottom - top;
    begin.renderPass = pw_ckey.vk_render_pass;
    begin.framebuffer = pw_ckey.vk_framebuffer;
    begin.renderArea = scissor;
    VK_CALL(vkCmdBeginRenderPass(vk_command_buffer, &begin, VK_SUBPASS_CONTENTS_INLINE));
    VK_CALL(vkCmdBindPipeline(vk_command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pw_ckey.vk_pipeline));
    VK_CALL(vkCmdBindDescriptorSets(vk_command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pw_ckey.vk_pipeline_layout,
            0, 1, &pw_ckey.vk_set, 0, NULL));
    /* the copy is in the image's corner: texel centres of the rectangle only */
    push.src[2] = (float)width / pw_ckey.tmp_width;
    push.src[3] = (float)height / pw_ckey.tmp_height;
    push.key[0] = colour_key->color_space_low_value;
    push.key[1] = colour_key->color_space_high_value;
    VK_CALL(vkCmdPushConstants(vk_command_buffer, pw_ckey.vk_pipeline_layout,
            VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT, 0, sizeof(push), &push));
    vk_viewport.x = dst_rect->left;
    vk_viewport.y = dst_rect->top;
    vk_viewport.width = dst_rect->right - dst_rect->left;
    vk_viewport.height = dst_rect->bottom - dst_rect->top;
    vk_viewport.minDepth = 0.0f;
    vk_viewport.maxDepth = 1.0f;
    VK_CALL(vkCmdSetViewport(vk_command_buffer, 0, 1, &vk_viewport));
    VK_CALL(vkCmdSetScissor(vk_command_buffer, 0, 1, &scissor));
    VK_CALL(vkCmdDraw(vk_command_buffer, 4, 1, 0, 0));
    VK_CALL(vkCmdEndRenderPass(vk_command_buffer));
    wined3d_context_vk_image_barrier(context_vk, vk_command_buffer,
            VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
            VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, vk_access_mask_from_bind_flags(dst_texture->resource.bind_flags),
            VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, dst_texture_vk->layout, dst_texture_vk->image.vk_image, &dst_range);

    wined3d_context_vk_reference_image(context_vk, &pw_ckey.tmp);
    wined3d_context_vk_reference_texture(context_vk, src_texture_vk);
    wined3d_context_vk_reference_texture(context_vk, dst_texture_vk);
    ++pw_ckey.blits;
    return true;
}

static DWORD vk_blitter_blit(struct wined3d_blitter *blitter, enum wined3d_blit_op op,''','GPU colour-keyed blits.')
revise('texture_vk.c',r'''    if (!vk_blitter_blit_supported(op, context, &src_texture->resource, src_rect, &dst_texture->resource, dst_rect,
            resolve_format))
        goto next;''',r'''    /* OrbisDesk W166 */
    if (op == WINED3D_BLIT_OP_COLOR_BLIT_CKEY && colour_key && pw_ckey_blit(context_vk, src_texture,
            src_sub_resource_idx, src_rect, dst_texture, dst_sub_resource_idx, dst_rect, colour_key))
    {
        wined3d_texture_validate_location(dst_texture, dst_sub_resource_idx, WINED3D_LOCATION_TEXTURE_RGB);
        wined3d_texture_invalidate_location(dst_texture, dst_sub_resource_idx, ~WINED3D_LOCATION_TEXTURE_RGB);
        if (!wined3d_texture_load_location(dst_texture, dst_sub_resource_idx, context, dst_location))
            ERR("Failed to load the destination sub-resource into %s.\n", wined3d_debug_location(dst_location));
        return dst_location | WINED3D_LOCATION_TEXTURE_RGB;
    }

    if (!vk_blitter_blit_supported(op, context, &src_texture->resource, src_rect, &dst_texture->resource, dst_rect,
            resolve_format))
        goto next;''','Colour-keyed blits go to the GPU path first.')

# W229: ddraw points its swapchain at a clipper's window (dlls/ddraw/surface.c SetClipper ->
# wined3d_swapchain_set_window), as quartz's VMR7 presenter does for the video window; the Vulkan
# swapchain kept the VkSurface of the first window (ddraw's hidden one) and the video never showed
# (W227). Before a present, a Vulkan swapchain made for another window is made again. The window
# each was made for is kept here, so wined3d_private.h (shared with units built by the pinned
# tree) does not change.
revise('swapchain.c','''static void wined3d_swapchain_vk_destroy_vulkan_swapchain(struct wined3d_swapchain_vk *swapchain_vk)
{''','''/* OrbisDesk W229: the window each Vulkan swapchain was made for */
static struct
{
    const struct wined3d_swapchain_vk *swapchain;
    HWND window;
} pw_vk_windows[32];

static void pw_vk_window_set(const struct wined3d_swapchain_vk *swapchain_vk, HWND window)
{
    unsigned int i, free_slot = ARRAY_SIZE(pw_vk_windows);

    for (i = 0; i < ARRAY_SIZE(pw_vk_windows); ++i)
    {
        if (pw_vk_windows[i].swapchain == swapchain_vk)
        {
            pw_vk_windows[i].window = window;
            return;
        }
        if (!pw_vk_windows[i].swapchain && free_slot == ARRAY_SIZE(pw_vk_windows))
            free_slot = i;
    }
    if (free_slot < ARRAY_SIZE(pw_vk_windows))
    {
        pw_vk_windows[free_slot].swapchain = swapchain_vk;
        pw_vk_windows[free_slot].window = window;
    }
}

static BOOL pw_vk_window_changed(const struct wined3d_swapchain_vk *swapchain_vk, HWND window, HWND *old)
{
    unsigned int i;

    for (i = 0; i < ARRAY_SIZE(pw_vk_windows); ++i)
    {
        if (pw_vk_windows[i].swapchain != swapchain_vk)
            continue;
        *old = pw_vk_windows[i].window;
        return *old != window;
    }
    return FALSE;
}

static void pw_vk_window_forget(const struct wined3d_swapchain_vk *swapchain_vk)
{
    unsigned int i;

    for (i = 0; i < ARRAY_SIZE(pw_vk_windows); ++i)
        if (pw_vk_windows[i].swapchain == swapchain_vk)
            pw_vk_windows[i].swapchain = NULL;
}

static void wined3d_swapchain_vk_destroy_vulkan_swapchain(struct wined3d_swapchain_vk *swapchain_vk)
{''','The window each Vulkan swapchain was made for.')
revise('swapchain.c','''    swapchain_vk->width = width;
    swapchain_vk->height = height;

    return WINED3D_OK;''','''    swapchain_vk->width = width;
    swapchain_vk->height = height;
    pw_vk_window_set(swapchain_vk, swapchain_vk->s.win_handle);

    return WINED3D_OK;''','A Vulkan swapchain records its window when made.')
revise('swapchain.c','''    wined3d_swapchain_vk_destroy_vulkan_swapchain(object);''','''    wined3d_swapchain_vk_destroy_vulkan_swapchain(object);
    pw_vk_window_forget(object);''','A freed swapchain leaves the window table.')
revise('swapchain.c','''    context_vk = wined3d_context_vk(context_acquire(swapchain->device, back_buffer, 0));

    if (!swapchain_vk->vk_swapchain || swapchain_present_is_partial_copy(swapchain, dst_rect))''','''    context_vk = wined3d_context_vk(context_acquire(swapchain->device, back_buffer, 0));

    {
        HWND old;

        if (swapchain_vk->vk_swapchain && pw_vk_window_changed(swapchain_vk, swapchain->win_handle, &old))
        {
            ERR("PWD3D swapchain_window from %p to %p\\n", old, swapchain->win_handle);
            if (FAILED(hr = wined3d_swapchain_vk_recreate(swapchain_vk)))
                ERR("PWD3D swapchain_window recreate failed, hr %#lx.\\n", hr);
        }
    }

    if (!swapchain_vk->vk_swapchain || swapchain_present_is_partial_copy(swapchain, dst_rect))''',
       'A Vulkan swapchain whose window changed is made again before it presents.')

# W251 (W249: SuperMarioKart in explorer's world): an unmapped BO for a DISCARD map is a logged fallback, never an
# assert exit; wined3d's global lock is released by a thread that ends holding it, and taken over from one that
# no longer exists (the i386 wined3d stays loaded across 32-bit guests).
UNITS=UNITS+('wined3d_main',)
revise('cs.c','''                /* adapter_alloc_bo() should have given us a mapped BO if we are
                 * discarding. */
                assert(flags & WINED3D_MAP_NOOVERWRITE);''','''                /* adapter_alloc_bo() should have given us a mapped BO if we are
                 * discarding. OrbisDesk W251: not when there was no memory for the map (W249) */
                if (!(flags & WINED3D_MAP_NOOVERWRITE))
                    ERR("PWD3D DISCARD map of resource %p got an unmapped BO; mapped through the CS instead.\\n", resource);''',
       'An unmapped BO for a DISCARD map goes through the CS (W251).')
revise('cs.c','''        if (!map_ptr)
        {
            assert(flags & WINED3D_MAP_NOOVERWRITE);
            WARN_(d3d_perf)("Not accelerating a NOOVERWRITE map because the sub-resource has no valid address.\\n");''','''        if (!map_ptr)
        {
            if (!(flags & WINED3D_MAP_NOOVERWRITE))  /* OrbisDesk W251 */
                ERR("PWD3D DISCARD map of resource %p has no address; mapped through the CS instead.\\n", resource);
            WARN_(d3d_perf)("Not accelerating a NOOVERWRITE map because the sub-resource has no valid address.\\n");''',
       'An unmapped BO for a DISCARD map goes through the CS (W251).')
revise('wined3d_main.c','''void WINAPI wined3d_mutex_lock(void)
{
    EnterCriticalSection(&wined3d_cs);
}''','''void WINAPI wined3d_mutex_lock(void)
{
    /* OrbisDesk W251: the i386 wined3d serves every 32-bit guest of explorer's world; a guest ended while one of
     * its threads held this lock (W249: SuperMarioKart's next start waited forever) */
    while (!TryEnterCriticalSection(&wined3d_cs))
    {
        DWORD owner = HandleToULong(wined3d_cs.OwningThread);
        HANDLE thread;
        DWORD wait;

        if (!owner) continue;  /* released meanwhile */
        if ((thread = OpenThread(SYNCHRONIZE, FALSE, owner)))
        {
            wait = WaitForSingleObject(thread, 0);
            CloseHandle(thread);
            if (wait != WAIT_OBJECT_0)
            {
                EnterCriticalSection(&wined3d_cs);  /* a live owner: wait as before */
                return;
            }
        }
        else if (GetLastError() != ERROR_INVALID_PARAMETER)
        {
            EnterCriticalSection(&wined3d_cs);
            return;
        }
        ERR("PWD3D wined3d lock held by ended thread %04lx (%ld): taken over\\n", owner, wined3d_cs.RecursionCount);
        if (InterlockedCompareExchangePointer((void **)&wined3d_cs.OwningThread, NULL, ULongToHandle(owner)) ==
            ULongToHandle(owner))
        {
            wined3d_cs.RecursionCount = 0;
            InterlockedExchange(&wined3d_cs.LockCount, -1);
        }
    }
}''','The wined3d lock is taken over from an ended thread (W251).')
revise('wined3d_main.c','''        case DLL_THREAD_DETACH:
            if (!wined3d_context_gl_set_current(NULL))''','''        case DLL_THREAD_DETACH:
            /* OrbisDesk W251: a thread that ends holding wined3d's lock (a guest's exit from inside a d3d call) */
            if (wined3d_cs.OwningThread == ULongToHandle(GetCurrentThreadId()))
            {
                ERR("PWD3D thread %04lx ends holding the wined3d lock (%ld): released\\n", GetCurrentThreadId(),
                    wined3d_cs.RecursionCount);
                while (wined3d_cs.OwningThread == ULongToHandle(GetCurrentThreadId()))
                    LeaveCriticalSection(&wined3d_cs);
            }
            if (!wined3d_context_gl_set_current(NULL))''','A thread ending with the wined3d lock releases it (W251).')

# W257 (W256: SuperMarioKart loaded libMangoHud but its instance never went through it): vkGetInstanceProcAddr from
# the Vulkan loader first, as DXVK since W247, so implicit layers (MangoHud) apply; winevulkan.dll if it fails.
# W258 put winevulkan.dll first; W287 the loader again, whose i386 build makes no DXGI factory
# (tools/vk-h0/build-vulkan-loader-i386.sh).
revise('adapter_vk.c','''    if (!(vk_info->vulkan_lib = LoadLibraryA("winevulkan.dll"))
            && !(vk_info->vulkan_lib = LoadLibraryA("vulkan-1.dll")))
    {
        WARN("Failed to load vulkan-1.dll.\\n");
        return FALSE;
    }

    vk_ops->vkGetInstanceProcAddr = (void *)GetProcAddress(vk_info->vulkan_lib, "vkGetInstanceProcAddr");
    if (!vk_ops->vkGetInstanceProcAddr)
    {
        FreeLibrary(vk_info->vulkan_lib);
        return FALSE;
    }

    return TRUE;''','''    /* OrbisDesk W287: the Vulkan loader first again, so MangoHud's implicit layer sits in this instance (W258 put
     * winevulkan.dll first: the loader's DXGI factory created Wine's dxgi, a wined3d adapter, the loader again). The
     * i386 loader makes no DXGI factory now (tools/vk-h0/build-vulkan-loader-i386.sh) */
    static const char *const names[] = {"vulkan-1.dll", "winevulkan.dll"};
    unsigned int i;

    for (i = 0; i < ARRAY_SIZE(names); ++i)
    {
        if (!(vk_info->vulkan_lib = LoadLibraryA(names[i])))
            continue;
        if ((vk_ops->vkGetInstanceProcAddr = (void *)GetProcAddress(vk_info->vulkan_lib, "vkGetInstanceProcAddr")))
        {
            ERR("PWD3D vulkan library=%s\\n", names[i]);
            return TRUE;
        }
        FreeLibrary(vk_info->vulkan_lib);
        vk_info->vulkan_lib = NULL;
    }
    WARN("Failed to load vulkan-1.dll.\\n");
    return FALSE;''','The Vulkan loader first, so layers apply (W257).')

# W262 (W261: Worms 4 ... and Age of Empires II's 8-bit mode): a swapchain without a Vulkan swapchain presents through
# GDI with its palette. AoE2's present changed the swap interval, the swapchain was made again for WINED3DFMT_P8_UINT,
# which no Vulkan swapchain format holds, and the blit acquired an image from the destroyed one (c0000005, exit 3).
revise('swapchain.c','''    free(swapchain_vk->vk_semaphores);
    VK_CALL(vkDestroySwapchainKHR(device_vk->vk_device, swapchain_vk->vk_swapchain, NULL));
    VK_CALL(vkDestroySurfaceKHR(vk_info->instance, swapchain_vk->vk_surface, NULL));
}''','''    free(swapchain_vk->vk_semaphores);
    if (swapchain_vk->vk_swapchain)
        VK_CALL(vkDestroySwapchainKHR(device_vk->vk_device, swapchain_vk->vk_swapchain, NULL));
    if (swapchain_vk->vk_surface)
        VK_CALL(vkDestroySurfaceKHR(vk_info->instance, swapchain_vk->vk_surface, NULL));
    /* OrbisDesk W262: nothing destroyed stays behind; a failed remake leaves no Vulkan swapchain (GDI present) */
    swapchain_vk->vk_images = NULL;
    swapchain_vk->vk_semaphores = NULL;
    swapchain_vk->image_count = 0;
    swapchain_vk->vk_swapchain = VK_NULL_HANDLE;
    swapchain_vk->vk_surface = VK_NULL_HANDLE;
}''','A destroyed Vulkan swapchain leaves no handles behind (W262).')
revise('swapchain.c','''    wined3d_swapchain_vk_set_swap_interval(swapchain_vk, swap_interval);

    present_idx = swapchain_vk->current++ % swapchain_vk->image_count;''','''    wined3d_swapchain_vk_set_swap_interval(swapchain_vk, swap_interval);

    if (!swapchain_vk->vk_swapchain)
    {
        /* OrbisDesk W262: its remake failed (a format no Vulkan swapchain holds, WINED3DFMT_P8_UINT) */
        ERR("PWD3D swapchain %p has no Vulkan swapchain for %s: GDI present.\\n",
                swapchain_vk, debug_d3dformat(desc->backbuffer_format));
        return VK_ERROR_SURFACE_LOST_KHR;
    }
    present_idx = swapchain_vk->current++ % swapchain_vk->image_count;''','No acquire from a swapchain that is not there (W262).')
revise('swapchain.c','''            else
            {
                ERR("Failed to blit image, vr %s.\\n", wined3d_debug_vkresult(vr));
            }''','''            else if (!swapchain_vk->vk_swapchain)
            {
                swapchain_blit_gdi(swapchain, &context_vk->c, src_rect, dst_rect);  /* OrbisDesk W262 */
            }
            else
            {
                ERR("Failed to blit image, vr %s.\\n", wined3d_debug_vkresult(vr));
            }''','The frame whose swapchain went goes through GDI (W262).')
revise('swapchain.c','''    TRACE("Created source DC %p, bitmap %p for backbuffer %p.\\n", src_dc, bitmap, back_buffer);
''','''    TRACE("Created source DC %p, bitmap %p for backbuffer %p.\\n", src_dc, bitmap, back_buffer);

    if (swapchain->palette)  /* OrbisDesk W262: a P8 back buffer through its palette (ddraw's primary palette) */
        wined3d_palette_apply_to_dc(swapchain->palette, src_dc);
''','A GDI present of a palettized back buffer uses its palette (W262).')
revise('swapchain.c','''    if (FAILED(hr = wined3d_swapchain_vk_create_vulkan_swapchain(swapchain_vk)))
    {
        WARN("Failed to create a Vulkan swapchain, hr %#lx.\\n", hr);
        return hr;
    }''','''    if (FAILED(hr = wined3d_swapchain_vk_create_vulkan_swapchain(swapchain_vk)))
    {
        /* OrbisDesk W262: it presents through GDI (a P8 mode from the start) */
        ERR("PWD3D swapchain %p for %s has no Vulkan swapchain, hr %#lx: GDI present.\\n",
                swapchain_vk, debug_d3dformat(desc->backbuffer_format), hr);
    }''','A swapchain without a Vulkan swapchain is made and presents through GDI (W262).')

# W287 (the overlay's GRAFICOS, native/hw_overlay.c): a program's HKCU\Software\Wine\AppDefaults\<exe>\Direct3D
# "renderer" wins over WINE_D3D_CONFIG, which the launcher (native/wine_hardware.c W127) and explorer's 32-bit world
# (tools/build-wow64-world-ps4.py W235) set to renderer=vulkan for every 32-bit program.
revise('wined3d_main.c','''static BOOL wined3d_dll_init(HINSTANCE hInstDLL)
{''','''/* OrbisDesk W287: the program's own AppDefaults\\<exe>\\Direct3D "renderer", before WINE_D3D_CONFIG */
static DWORD pw_app_renderer(HKEY appkey, char *buffer, DWORD size)
{
    if (!appkey || RegQueryValueExA(appkey, "renderer", 0, NULL, (BYTE *)buffer, &size))
        return ERROR_FILE_NOT_FOUND;
    ERR("PWD3D renderer=%s from the program's AppDefaults (over WINE_D3D_CONFIG)\\n", debugstr_a(buffer));
    return 0;
}

static BOOL wined3d_dll_init(HINSTANCE hInstDLL)
{''',"The program's own renderer is read first (W287).")
revise('wined3d_main.c','''        if (!get_config_key(hkey, appkey, env, "renderer", buffer, size))''',
       '''        if (!pw_app_renderer(appkey, buffer, size) || !get_config_key(hkey, appkey, env, "renderer", buffer, size))''',
       "The program's own renderer wins over WINE_D3D_CONFIG (W287).")
# W288 (W287: SuperMarioKart's renderer was set to "gl" from the overlay, but its next start used Vulkan again:
# wined3d stayed loaded in explorer's 32-bit world after the first run, and the renderer is read only when the DLL
# loads). Each wined3d_create reads it again for the program asking: its AppDefaults\<exe>\Direct3D "renderer",
# else the world's WINE_D3D_CONFIG, else what wined3d_dll_init chose. GetModuleFileNameW(NULL) names the guest
# (tools/build-guest-hw.py).
revise('wined3d_main.c','''struct wined3d * CDECL wined3d_create(uint32_t flags)
{''','''/* OrbisDesk W288: the renderer for the program creating this wined3d object */
static BOOL pw_parse_renderer(const char *value, enum wined3d_renderer *renderer)
{
    if (!strcmp(value, "vulkan")) *renderer = WINED3D_RENDERER_VULKAN;
    else if (!strcmp(value, "gl")) *renderer = WINED3D_RENDERER_OPENGL;
    else if (!strcmp(value, "no3d")) *renderer = WINED3D_RENDERER_NO3D;
    else return FALSE;
    return TRUE;
}

static void pw_program_renderer(void)
{
    static const WCHAR prefix[] = L"Software\\\\Wine\\\\AppDefaults\\\\";
    static BOOL saved;
    static enum wined3d_renderer world;
    enum wined3d_renderer renderer;
    WCHAR path[MAX_PATH], key_name[MAX_PATH + 64], *name, *p;
    char buffer[64], env[256], *found, *end;
    const char *source = "world";
    DWORD size = sizeof(buffer), len;
    HKEY key;

    if (!saved)
    {
        world = wined3d_settings.renderer;
        len = GetEnvironmentVariableA("WINE_D3D_CONFIG", env, sizeof(env));
        if (len && len < sizeof(env) && (found = strstr(env, "renderer=")))
        {
            found += 9;
            if ((end = strpbrk(found, ",; "))) *end = 0;
            if (!pw_parse_renderer(found, &world)) world = wined3d_settings.renderer;
        }
        saved = TRUE;
    }
    renderer = world;
    if (GetModuleFileNameW(NULL, path, ARRAY_SIZE(path)))
    {
        for (name = p = path; *p; p++) if (*p == '\\\\' || *p == '/') name = p + 1;
        lstrcpyW(key_name, prefix);
        lstrcatW(key_name, name);
        lstrcatW(key_name, L"\\\\Direct3D");
        if (!RegOpenKeyExW(HKEY_CURRENT_USER, key_name, 0, KEY_READ, &key))
        {
            if (!RegQueryValueExA(key, "renderer", NULL, NULL, (BYTE *)buffer, &size) && size < sizeof(buffer))
            {
                buffer[size] = 0;
                if (pw_parse_renderer(buffer, &renderer)) source = "program";
                else ERR("PWD3D renderer %s of %s is not vulkan, gl or no3d; the world's is used\\n",
                         debugstr_a(buffer), debugstr_w(name));
            }
            RegCloseKey(key);
        }
    }
    else name = path, path[0] = 0;
    if (renderer != wined3d_settings.renderer || !strcmp(source, "program"))
        ERR("PWD3D renderer=%s for %s from the %s (was %s)\\n",
            renderer == WINED3D_RENDERER_VULKAN ? "vulkan" : renderer == WINED3D_RENDERER_OPENGL ? "gl" :
            renderer == WINED3D_RENDERER_NO3D ? "no3d" : "auto", debugstr_w(name), source,
            wined3d_settings.renderer == WINED3D_RENDERER_VULKAN ? "vulkan" :
            wined3d_settings.renderer == WINED3D_RENDERER_OPENGL ? "gl" :
            wined3d_settings.renderer == WINED3D_RENDERER_NO3D ? "no3d" : "auto");
    wined3d_settings.renderer = renderer;
}

struct wined3d * CDECL wined3d_create(uint32_t flags)
{''',"The renderer is read again for each program at wined3d_create (W288).")
revise('wined3d_main.c','''    if (wined3d_settings.renderer == WINED3D_RENDERER_NO3D)
        flags |= WINED3D_NO3D;''','''    pw_program_renderer();  /* W288 */
    if (wined3d_settings.renderer == WINED3D_RENDERER_NO3D)
        flags |= WINED3D_NO3D;''',"Each wined3d_create takes its program's renderer (W288).")

dry=subprocess.run(['make','-n']+[f'-W../../source/dlls/wined3d/{u}.c' for u in UNITS]+
                   [f'dlls/wined3d/{ARCH}/wined3d.dll'],cwd=BUILD,capture_output=True,text=True,check=True).stdout
dry=dry.replace('\\\n',' ')
commands=[]
for line in dry.splitlines():
    if 'dlls/wined3d/' not in line:continue
    for u in UNITS:line=line.replace(f'../../source/dlls/wined3d/{u}.c',str(overlay/(u+'.c')))
    # Only the revised units and the link go to work/; the other objects are the pinned build's.
    for name in [u+'.o' for u in UNITS]+['wined3d.dll']:
        line=line.replace(f'dlls/wined3d/{ARCH}/'+name,str(work/name))
    commands.append(line)
if not all(any(str(overlay/(u+'.c')) in c for c in commands) for u in UNITS) or not any(str(work/'wined3d.dll') in c for c in commands):
    raise SystemExit('make -n did not give the wined3d commands:\n'+dry[-2000:])
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    if 'warning' in run.stderr:print(run.stderr)
target=out/'wined3d.dll';shutil.copyfile(work/'wined3d.dll',target)
manifest={'schema_version':1,'wine_commit':commit,'arch':ARCH,'wined3d':{'path':'wined3d.dll','sha256':sha(target)},
          'revisions':revisions,'commands':commands,
          'overlay_sha256':{u+'.c':sha(overlay/(u+'.c')) for u in UNITS},
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'wined3d':str(target.relative_to(ROOT)),'sha256':manifest['wined3d']['sha256'],'revisions':len(revisions)}))
