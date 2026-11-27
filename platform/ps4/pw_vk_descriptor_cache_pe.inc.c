/* SPDX-License-Identifier: LGPL-2.1-or-later
 * PE32 adapter, included after the original batch core. Cached outputs are
 * copied synchronously; no assumption that a mapped destination is GPU-only. */
#ifndef PW_DC_PTR
#define PW_DC_PTR(p) ((uint32_t)(uintptr_t)(p))
#endif
static UINT64 descriptor_read(UINT64 *value) {return InterlockedCompareExchange64((LONG64 *)value,0,0);}
static void descriptor_count(UINT64 *value) {if(stats_enabled)InterlockedIncrement64((LONG64 *)value);}
static int descriptor_alias(const void *out,size_t bytes,const void *in,size_t size)
{
 uintptr_t a=(uintptr_t)out,b=(uintptr_t)in;
 return bytes>UINTPTR_MAX-a||size>UINTPTR_MAX-b||(a<b+size&&b<a+bytes);
}
static int descriptor_key(const struct vkGetDescriptorEXT_params *q,struct pw_dc_key *key)
{
 const VkDescriptorGetInfoEXT *info=q->pDescriptorInfo;
 const VkDescriptorImageInfo *image=NULL;
 const VkDescriptorAddressInfoEXT *address=NULL;
 if(!q->device||!q->pDescriptor||!info||!q->dataSize||q->dataSize>PW_DC_MAX_BYTES||
    info->sType!=VK_STRUCTURE_TYPE_DESCRIPTOR_GET_INFO_EXT||info->pNext||
    descriptor_alias(q->pDescriptor,q->dataSize,info,sizeof(*info)))return 0;
 memset(key,0,sizeof(*key));key->words[0]=(UINT_PTR)q->device;key->words[1]=info->type;key->words[2]=q->dataSize;
 switch(info->type){
 case VK_DESCRIPTOR_TYPE_SAMPLER:
  if(!info->data.pSampler||descriptor_alias(q->pDescriptor,q->dataSize,info->data.pSampler,sizeof(VkSampler)))return 0;
  key->words[3]=*info->data.pSampler;key->words[6]=1;return 1;
 case VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER:image=info->data.pCombinedImageSampler;break;
 case VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE:image=info->data.pSampledImage;break;
 case VK_DESCRIPTOR_TYPE_STORAGE_IMAGE:image=info->data.pStorageImage;break;
 case VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT:image=info->data.pInputAttachmentImage;break;
 case VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER:address=info->data.pUniformBuffer;break;
 case VK_DESCRIPTOR_TYPE_STORAGE_BUFFER:address=info->data.pStorageBuffer;break;
 case VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER:address=info->data.pUniformTexelBuffer;break;
 case VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER:address=info->data.pStorageTexelBuffer;break;
 default:return 0;
 }
 if(image){
  if(descriptor_alias(q->pDescriptor,q->dataSize,image,sizeof(*image)))return 0;
  key->words[3]=image->imageView;key->words[4]=info->type==VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER?image->sampler:0;
  key->words[5]=(uint32_t)image->imageLayout;key->words[6]=1;
 }
 if(address){
  if(address->sType!=VK_STRUCTURE_TYPE_DESCRIPTOR_ADDRESS_INFO_EXT||address->pNext||
     descriptor_alias(q->pDescriptor,q->dataSize,address,sizeof(*address)))return 0;
  key->words[3]=address->address;key->words[4]=address->range;key->words[5]=address->format;key->words[6]=1;
 }
 return 1;
}
static int descriptor_mutates(unsigned code)
{
 switch(code){
 case unix_vkDestroyDevice:case unix_vkDestroyInstance:case unix_vkDestroyImageView:
 case unix_vkDestroySampler:case unix_vkDestroySamplerYcbcrConversion:case unix_vkDestroySamplerYcbcrConversionKHR:
 case unix_vkDestroyImage:case unix_vkDestroyBuffer:case unix_vkDestroyBufferView:case unix_vkDestroySwapchainKHR:
 case unix_vkFreeMemory:case unix_vkBindBufferMemory:case unix_vkBindBufferMemory2:case unix_vkBindBufferMemory2KHR:
 case unix_vkBindImageMemory:case unix_vkBindImageMemory2:case unix_vkBindImageMemory2KHR:case unix_vkQueueBindSparse:
  return 1;
 default:return 0;
 }
}
static void descriptor_report(UINT64 ordinal)
{
 if(!stats_enabled)return;
 WINE_MESSAGE("PW_DESCRIPTOR_CACHE version=1 present=%llu requested=%u supported=%u disabled=%ld requests=%llu hits=%llu misses=%llu bypass=%llu audits=%llu rejected=%llu invalidations=%llu epoch=%llu\n",
  ordinal,descriptor_requested,(unsigned)descriptor_capable,InterlockedCompareExchange(&descriptor_bad,0,0),
  descriptor_read(&descriptor_requests),descriptor_read(&descriptor_hits),descriptor_read(&descriptor_misses),
  descriptor_read(&descriptor_bypass),descriptor_read(&descriptor_audits),descriptor_read(&descriptor_rejected),
  descriptor_read(&descriptor_invalidations),descriptor_read(&descriptor_epoch));
 WINE_MESSAGE("PW_DESCRIPTOR_TYPES present=%llu sampler=%llu combined=%llu sampled=%llu storage_image=%llu uniform_texel=%llu storage_texel=%llu uniform_buffer=%llu storage_buffer=%llu input_attachment=%llu other=%llu\n",
  ordinal,descriptor_read(&descriptor_types[0]),descriptor_read(&descriptor_types[1]),descriptor_read(&descriptor_types[2]),
  descriptor_read(&descriptor_types[3]),descriptor_read(&descriptor_types[4]),descriptor_read(&descriptor_types[5]),
  descriptor_read(&descriptor_types[6]),descriptor_read(&descriptor_types[7]),descriptor_read(&descriptor_types[10]),descriptor_read(&descriptor_types[11]));
}
static NTSTATUS descriptor_get(struct vkGetDescriptorEXT_params *q)
{
 struct pw_dc_key key;struct producer *p;const struct pw_dc_value *hit;
 struct pw_dc_value fresh;UINT64 epoch;NTSTATUS status;int audit=0;
 DECLSPEC_ALIGN(16) unsigned char a[PW_DC_MAX_BYTES],b[PW_DC_MAX_BYTES];
 struct vkGetDescriptorEXT_params qa,qb;struct pw_dc_query query;
 descriptor_count(&descriptor_requests);
 if(q->pDescriptorInfo){unsigned t=q->pDescriptorInfo->type;descriptor_count(&descriptor_types[t<11?t:11]);}
 if(!descriptor_key(q,&key)||(p=producer())==NULL){descriptor_count(&descriptor_bypass);return pw_vk_batch_call_core(unix_vkGetDescriptorEXT,q);}
 epoch=descriptor_read(&descriptor_epoch);hit=pw_dc_find(&p->descriptors,&key,epoch);
 if(hit){
  ++p->descriptor_hit_sequence;
  audit=p->descriptor_hit_sequence<=16||!(p->descriptor_hit_sequence%4096);
  if(!audit){pw_dc_copy(q->pDescriptor,hit);descriptor_count(&descriptor_hits);return STATUS_SUCCESS;}
  descriptor_count(&descriptor_audits);
 }else descriptor_count(&descriptor_misses);
 memset(a,0xa5,q->dataSize);memset(b,0x5a,q->dataSize);qa=qb=*q;qa.pDescriptor=a;qb.pDescriptor=b;
 query=(struct pw_dc_query){1,PW_DC_PTR(&qa),PW_DC_PTR(&qb),(uint32_t)q->dataSize};
 enter();fallback_total++;if(fallback_profile)fallback_counts[unix_vkGetDescriptorEXT]++;
 status=flush_call_query(unix_vkGetDescriptorEXT,q,&query);leave();
 if(status||!pw_dc_learn(&fresh,a,b,(unsigned)q->dataSize)){
  descriptor_count(&descriptor_rejected);InterlockedExchange(&descriptor_bad,1);
  ERR("PW_DESCRIPTOR_CACHE disabled: driver query failure or non-deterministic output\n");
  return pw_vk_batch_call_core(unix_vkGetDescriptorEXT,q);
 }
 if(hit&&!pw_dc_equal(hit,&fresh)){
  descriptor_count(&descriptor_rejected);InterlockedExchange(&descriptor_bad,1);
  ERR("PW_DESCRIPTOR_CACHE disabled: audit mismatch\n");
 }
 pw_dc_copy(q->pDescriptor,&fresh);
 if(epoch==descriptor_read(&descriptor_epoch)&&!InterlockedCompareExchange(&descriptor_bad,0,0))pw_dc_store(&p->descriptors,&key,epoch,&fresh);
 if(hit)descriptor_count(&descriptor_hits);
 return STATUS_SUCCESS;
}
NTSTATUS pw_vk_batch_call(unsigned int code,void *args)
{
 InitOnceExecuteOnce(&once,initialize,NULL,NULL);
 if(!enabled||InterlockedCompareExchange(&sticky_disabled,0,0)){NTSTATUS status=raw_call(code,args);snapshot(code,args);return status;}
 if(descriptor_requested&&descriptor_capable&&!InterlockedCompareExchange(&descriptor_bad,0,0)){
  if(descriptor_mutates(code)){
   descriptor_count(&descriptor_invalidations);
   if(!InterlockedIncrement64((LONG64 *)&descriptor_epoch))InterlockedExchange(&descriptor_bad,1);
  }
  if(code==unix_vkGetDescriptorEXT)return descriptor_get(args);
 }
 return pw_vk_batch_call_core(code,args);
}
