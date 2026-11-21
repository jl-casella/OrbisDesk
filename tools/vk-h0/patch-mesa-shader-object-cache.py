#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""04.28 (docs/SHADER_CACHE.md): the two gaps the 04.27 console runs showed in RADV's disk cache (Crema's tree,
VARIANT=wine only, __PS4__ only).

1. src/util/os_misc.c: Mesa reads MESA_SHADER_CACHE_DIR and XDG_CACHE_HOME with secure_getenv. In the title's ELF the
   OpenOrbis libc's secure flag is set, so secure_getenv returns NULL for every name (run-0244..0246: the directory
   the launcher set was ignored; RADV devices created before Wine sets HOME had no cache at all, among them the
   sink's, which compiles frame generation's compute pipelines again on every launch, ~1.4 s). A title has no
   setuid boundary to protect: on __PS4__ those lookups use getenv.
2. src/amd/vulkan/radv_shader_object.c: RADV caches pipelines, not VK_EXT_shader_object shaders, which it compiles
   on every vkCreateShadersEXT. Zink uses shader objects on RADV and its own disk cache does not exist in a Windows
   build, so every GL shader was compiled again on every run (run-0245: 282 of 290 misses, 6.4 s). Here an
   unlinked SPIR-V shader object is looked up in the device's disk cache under a key made of the create info
   (code, entry point, stages, flags, specialization, push constant ranges, set layout hashes, required subgroup
   size) and RADV's device cache hash; a hit is created from the stored vkGetShaderBinaryDataEXT blob, a miss is
   compiled as before and its blob stored. Linked shaders, create infos with other pNext structs and devices that
   RADV would not cache for (RADV_DEBUG=nocache, ACO debug flags, printf/VA validation, shader info kept) compile
   as before.
patch-mesa-shader-object-cache.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib,sys
mesa=pathlib.Path(sys.argv[1])
MARK='OrbisDesk 04.28 shader cache'

def patch(path,edits):
    target=mesa/path;text=normalize_marker(target.read_text())
    if MARK in text:
        print(path,'already patched');return
    for old,new in edits:
        if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:70])
        text=text.replace(old,new,1)
    target.write_text(text);print(path,'patched')

patch('src/util/os_misc.c',[
('''   if (use_secure_getenv) {
#ifdef HAVE_SECURE_GETENV
      opt = secure_getenv(name);''','''   if (use_secure_getenv) {
#if defined(HAVE_SECURE_GETENV) && !defined(__PS4__) /* '''+MARK+''': the title's libc answers NULL */
      opt = secure_getenv(name);'''),
])

HELPERS='''#ifdef __PS4__ /* '''+MARK+''' */
/* The key of an unlinked SPIR-V shader object in the device's disk cache, or false when it is not cached. */
static bool
pw_shobj_cache_key(struct radv_device *device, const VkShaderCreateInfoEXT *info, cache_key key)
{
   const struct radv_physical_device *pdev = radv_device_physical(device);
   const struct radv_instance *instance = radv_physical_device_instance(pdev);

   if (!pdev->vk.disk_cache || info->codeType != VK_SHADER_CODE_TYPE_SPIRV_EXT ||
       (info->flags & VK_SHADER_CREATE_LINK_STAGE_BIT_EXT))
      return false;
   /* the cases radv_is_cache_disabled (radv_pipeline_cache.c) and the shader info keeping exclude */
   if (device->printf.buffer_addr || device->valid_vas_addr || device->keep_shader_info ||
       (instance->debug_flags & RADV_DEBUG_NO_CACHE) || (pdev->use_llvm ? 0 : aco_get_codegen_flags()))
      return false;

   uint32_t subgroup_size = 0;
   vk_foreach_struct_const (ext, info->pNext) {
      if (ext->sType != VK_STRUCTURE_TYPE_SHADER_REQUIRED_SUBGROUP_SIZE_CREATE_INFO_EXT)
         return false; /* anything else may change the code: not cached */
      subgroup_size = ((const VkShaderRequiredSubgroupSizeCreateInfoEXT *)ext)->requiredSubgroupSize;
   }

   static const char tag[] = "OrbisDesk radv shader object v1";
   struct mesa_sha1 ctx;
   unsigned char hash[SHA1_DIGEST_LENGTH];
   _mesa_sha1_init(&ctx);
   _mesa_sha1_update(&ctx, tag, sizeof(tag));
   _mesa_sha1_update(&ctx, device->cache_hash, sizeof(device->cache_hash));
   const uint64_t words[6] = {info->flags, info->stage, info->nextStage, info->codeSize, subgroup_size,
                              info->setLayoutCount};
   _mesa_sha1_update(&ctx, words, sizeof(words));
   _mesa_sha1_update(&ctx, info->pCode, info->codeSize);
   if (info->pName)
      _mesa_sha1_update(&ctx, info->pName, strlen(info->pName) + 1);
   for (uint32_t i = 0; i < info->setLayoutCount; i++) {
      VK_FROM_HANDLE(radv_descriptor_set_layout, set_layout, info->pSetLayouts[i]);
      const uint32_t present = set_layout != NULL;
      _mesa_sha1_update(&ctx, &present, sizeof(present));
      if (set_layout)
         _mesa_sha1_update(&ctx, set_layout->hash, sizeof(set_layout->hash));
   }
   _mesa_sha1_update(&ctx, &info->pushConstantRangeCount, sizeof(info->pushConstantRangeCount));
   if (info->pushConstantRangeCount)
      _mesa_sha1_update(&ctx, info->pPushConstantRanges,
                        info->pushConstantRangeCount * sizeof(*info->pPushConstantRanges));
   const VkSpecializationInfo *spec = info->pSpecializationInfo;
   const uint32_t spec_count = spec ? spec->mapEntryCount : 0;
   _mesa_sha1_update(&ctx, &spec_count, sizeof(spec_count));
   if (spec) {
      if (spec->mapEntryCount)
         _mesa_sha1_update(&ctx, spec->pMapEntries, spec->mapEntryCount * sizeof(*spec->pMapEntries));
      const uint64_t data_size = spec->dataSize;
      _mesa_sha1_update(&ctx, &data_size, sizeof(data_size));
      if (spec->dataSize)
         _mesa_sha1_update(&ctx, spec->pData, spec->dataSize);
   }
   _mesa_sha1_final(&ctx, hash);
   disk_cache_compute_key(pdev->vk.disk_cache, hash, sizeof(hash), key);
   return true;
}

/* A binary-created object points into the creator's blob; give each variant its own copy, so the object owns
 * them as a SPIR-V-created one does (radv_shader_object_destroy_variant frees them). */
static bool
pw_shobj_own(struct radv_shader_binary **binary)
{
   if (!*binary)
      return true;
   void *copy = malloc((*binary)->total_size);
   if (!copy)
      return false;
   memcpy(copy, *binary, (*binary)->total_size);
   *binary = copy;
   return true;
}

static void
pw_shobj_drop(struct radv_device *device, struct radv_shader_object *obj)
{
   struct radv_shader *shaders[] = {obj->shader, obj->as_es.shader, obj->as_ls.shader, obj->gs.copy_shader};
   for (unsigned i = 0; i < ARRAY_SIZE(shaders); i++) {
      if (shaders[i])
         radv_shader_unref(device, shaders[i]);
   }
   obj->shader = obj->as_es.shader = obj->as_ls.shader = obj->gs.copy_shader = NULL;
   obj->binary = obj->as_es.binary = obj->as_ls.binary = obj->gs.copy_binary = NULL;
}
#endif

static VkResult
radv_shader_object_create(VkDevice _device, const VkShaderCreateInfoEXT *pCreateInfo,'''

patch('src/amd/vulkan/radv_shader_object.c',[
('#include "pw_pipeline_trace.h" /* OrbisDesk 04.27 pipeline trace */\n',
 '#include "pw_pipeline_trace.h" /* OrbisDesk 04.27 pipeline trace */\n'
 '#ifdef __PS4__ /* '+MARK+' */\n#include "aco_interface.h"\n#include "radv_debug.h"\n#include "radv_descriptor_set.h"\n'
 '#include "radv_instance.h"\n#include "util/disk_cache.h"\n#include "util/mesa-sha1.h"\n#include "vk_util.h"\n#endif\n'),
('''static VkResult
radv_shader_object_create(VkDevice _device, const VkShaderCreateInfoEXT *pCreateInfo,''',HELPERS),
('''   result = radv_shader_object_init(shader_obj, device, pCreateInfo);
   if (result != VK_SUCCESS) {
      radv_shader_object_destroy(device, shader_obj, pAllocator);
      return result;
   }

   *pShader = radv_shader_object_to_handle(shader_obj);
''','''#ifdef __PS4__ /* '''+MARK+''' */
   cache_key pw_key;
   const bool pw_cached = pw_shobj_cache_key(device, pCreateInfo, pw_key);
   struct disk_cache *pw_disk = radv_device_physical(device)->vk.disk_cache;
   if (pw_cached) {
      size_t pw_size = 0;
      void *pw_data = disk_cache_get(pw_disk, pw_key, &pw_size);
      if (pw_data) {
         VkShaderCreateInfoEXT pw_info = *pCreateInfo;
         pw_info.codeType = VK_SHADER_CODE_TYPE_BINARY_EXT;
         pw_info.codeSize = pw_size;
         pw_info.pCode = pw_data;
         result = radv_shader_object_init(shader_obj, device, &pw_info);
         if (result == VK_SUCCESS) {
            if (pw_shobj_own(&shader_obj->binary) && pw_shobj_own(&shader_obj->as_es.binary) &&
                pw_shobj_own(&shader_obj->as_ls.binary) && pw_shobj_own(&shader_obj->gs.copy_binary)) {
               shader_obj->code_type = VK_SHADER_CODE_TYPE_SPIRV_EXT;
               free(pw_data);
            } /* else out of memory: the blob stays, owned by nobody (a leak, not a dangling pointer) */
            pw_vk_cache_found = 1;
            pw_vk_cache_disk = 1;
            *pShader = radv_shader_object_to_handle(shader_obj);
            return VK_SUCCESS;
         }
         /* a stale or damaged entry: compile from SPIR-V */
         pw_shobj_drop(device, shader_obj);
         free(pw_data);
      }
   }
#endif
   result = radv_shader_object_init(shader_obj, device, pCreateInfo);
   if (result != VK_SUCCESS) {
      radv_shader_object_destroy(device, shader_obj, pAllocator);
      return result;
   }

   *pShader = radv_shader_object_to_handle(shader_obj);
#ifdef __PS4__ /* '''+MARK+''' */
   if (pw_cached) {
      size_t pw_size = 0;
      void *pw_blob = NULL;
      if (radv_GetShaderBinaryDataEXT(_device, *pShader, &pw_size, NULL) == VK_SUCCESS && pw_size &&
          (pw_blob = malloc(pw_size)) &&
          radv_GetShaderBinaryDataEXT(_device, *pShader, &pw_size, pw_blob) == VK_SUCCESS)
         disk_cache_put(pw_disk, pw_key, pw_blob, pw_size, NULL);
      free(pw_blob);
   }
#endif
'''),
])
