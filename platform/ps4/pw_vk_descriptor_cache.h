/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_VK_DESCRIPTOR_CACHE_H
#define PW_VK_DESCRIPTOR_CACHE_H
#include <stdint.h>
#include <string.h>
#define PW_DC_MAX_BYTES 128u
#define PW_DC_SETS 1024u
#define PW_DC_WAYS 2u
#define PW_DC_CAP_NAME "__wine_pw_vk_descriptor_cache_v1"
#define PW_DC_CAP 0x50574451u
#define PW_DC_BATCH_VERSION 0x44534301u
/* Private, negotiated extension of the existing batch entry. Standard batch
 * versions and record framing remain unchanged. All pointers are PE32. */
struct pw_dc_query {uint32_t version,args_a,args_b,bytes;};
struct pw_dc_key {uint64_t words[8];};
struct pw_dc_value {uint32_t size,whole;unsigned char data[PW_DC_MAX_BYTES],written[PW_DC_MAX_BYTES];};
struct pw_dc_entry {uint64_t epoch;struct pw_dc_key key;struct pw_dc_value value;};
struct pw_dc_cache {struct pw_dc_entry entries[PW_DC_SETS][PW_DC_WAYS];unsigned char next[PW_DC_SETS];};
static inline unsigned pw_dc_hash(const struct pw_dc_key *key)
{
    uint32_t h=2166136261u;
    for(unsigned i=0;i<8;i++) {h=(h^(uint32_t)key->words[i])*16777619u;h=(h^(uint32_t)(key->words[i]>>32))*16777619u;}
    return (h^(h>>16))&(PW_DC_SETS-1);
}
static inline const struct pw_dc_value *pw_dc_find(struct pw_dc_cache *cache,const struct pw_dc_key *key,uint64_t epoch)
{
    unsigned set=pw_dc_hash(key);
    if(!epoch)return NULL;
    for(unsigned i=0;i<PW_DC_WAYS;i++) {
        struct pw_dc_entry *e=&cache->entries[set][i];
        if(e->epoch==epoch&&!memcmp(&e->key,key,sizeof(*key))) {cache->next[set]=(unsigned char)(1-i);return &e->value;}
    }
    return NULL;
}
static inline void pw_dc_store(struct pw_dc_cache *cache,const struct pw_dc_key *key,uint64_t epoch,const struct pw_dc_value *value)
{
    unsigned set=pw_dc_hash(key),slot=cache->next[set];
    if(!epoch)return;
    for(unsigned i=0;i<PW_DC_WAYS;i++) if(cache->entries[set][i].epoch!=epoch) {slot=i;break;}
    struct pw_dc_entry *e=&cache->entries[set][slot];
    e->key=*key;e->value=*value;e->epoch=epoch;cache->next[set]=(unsigned char)(1-slot);
}
/* Two real driver queries with distinct initial bytes identify exactly which
 * bytes RADV writes. Preserve caller-owned gaps/padding, including combined
 * image/sampler layouts. Reject differences not explained by untouched bytes. */
static inline int pw_dc_learn(struct pw_dc_value *value,const unsigned char *a,const unsigned char *b,unsigned bytes)
{
    if(!bytes||bytes>PW_DC_MAX_BYTES)return 0;
    memset(value,0,sizeof(*value));value->size=bytes;value->whole=1;
    for(unsigned i=0;i<bytes;i++) {
        if(a[i]==b[i]) {value->data[i]=a[i];value->written[i]=1;}
        else if(a[i]==0xa5&&b[i]==0x5a) value->whole=0;
        else return 0;
    }
    return 1;
}
static inline void pw_dc_copy(void *destination,const struct pw_dc_value *value)
{
    if(value->whole)memcpy(destination,value->data,value->size);
    else for(unsigned i=0;i<value->size;i++) if(value->written[i])((unsigned char *)destination)[i]=value->data[i];
}
static inline int pw_dc_equal(const struct pw_dc_value *a,const struct pw_dc_value *b)
{
    if(a->size!=b->size)return 0;
    for(unsigned i=0;i<a->size;i++) if(a->written[i]!=b->written[i]||(a->written[i]&&a->data[i]!=b->data[i]))return 0;
    return 1;
}
#endif
