<a id="w167-agrupamiento-de-llamadas-vulkan-de-32-bits-activado-fase-6"></a>


# W167: Vulkan call grouping of 32 bits activated (phase 6)

[English](HARDWARE_W167.md) | [Español](HARDWARE_W167-es.md)

APP_VER 02.66. Base W166.

<a id="cambio"></a>


## Change

`native/wine_hardware.c`: in the 32 bit runs add
- `PW_VK_BATCH=1`: light the grouping of W166;
- `PW_VK_BATCH_STATS=1`: one line `PW_VK_BATCH` per present, with the glued records, the emptied ones, those travelling next to another call and the calls that continue to go alone;
- `PW_VK_BATCH_FALLBACK_PROFILE=1`: every 300 presents, `PW_VK_FALLBACK_TOP` with functions that were most often alone.

The layout of the launcher's arguments goes from 20 to 24 fixed places.

The two diagnoses are for this test; are removed when measured.

<a id="qué-se-espera"></a>


## What is expected

- `PW_VK_BATCH … enabled=1 negotiated=1`.
- **Profile of wow64native:** in the thread of wined3d, much less called Unix per second and less time of change of FS.
- **Game:** more FPS.
- **Risk:** with active grouping, an error in reproduction can draw badly or close the game. prospero-win ends the process in the face of a failure of order or reproduction (`PW_VK_BATCH fatal`).

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w167/physical/20261103T173339Z`, `run-0002.log` (SuperMarioKart, ~ 150 s). User response: "Faster, good." There was no `PW_VK_BATCH fatal`.

**Group** (`PW_VK_BATCH`, present 8455):
- `enabled=1 negotiated=1`;
- 9,18 million collate records, in 1,24 million emptied (~ 7,4 emptied records);
- 98% of the emptied traveled along with another call; 20.007 were released;
- 1,53 million calls continued to go alone (`fallback`), in total 1,55 million crosses to Unix for 8.455 pictures.

**Profile of wow64native, thread of wined3d:**

| | W166 | W167 |
|---|---|---|
|Unix calls per second| ~73.000 | ~11.600 |
|Change of FS| 16,4 % | 3,8 % |
| Unix | 24,7 % | 34,3 % |
| Syscalls | 34,1 % | 28,5 % |
| 32 bits | 24,8 % | 33,4 % |

**FPS of the race** (`PWVK present fps`): 27 - 74. The majority between 33 and 60, with sections of 45 - 63 that were not shown before. In W165 - W166 were 27 - 53.

**Calls that continue to go the most alone** (`PW_VK_FALLBACK_TOP`, presents 8100 - 8400:

|Function|Calls|By table|
|---|---|---|
| `vkAllocateDescriptorSets` | 55.600 | ~185 |
| `vkCreateFramebuffer` | 29.490 | ~98 |
| `vkCreateImageView` | 4.200 | ~14 |
| `vkCreateImage`, `vkBindImageMemory`, `vkGetImageMemoryRequirements` |2.100 each| ~7 |

The image (and part of the framebuffers and views) comes from the key color copies of W165: each copy creates a temporary image, two views and a framebuffer. They can be reused between copies.
