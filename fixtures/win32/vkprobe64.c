/* SPDX-License-Identifier: LGPL-2.1-or-later
 * W071 (H2): a Windows console program that uses Vulkan through vulkan-1.dll, as any
 * Windows program does: instance, physical devices, device, and a GPU fill of a
 * host-visible buffer checked by the CPU, with timings. It prints to the console and to
 * C:\orbis\vkprobe64.txt. Each Vulkan result is printed; a failure stops the probe. */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <vulkan/vulkan_core.h>

static FILE *out;

static void say( const char *format, ... )
{
    va_list args;
    va_start( args, format );
    vprintf( format, args );
    va_end( args );
    if (out)
    {
        va_start( args, format );
        vfprintf( out, format, args );
        va_end( args );
        fflush( out );
    }
}

#define CHECK(call) do { VkResult r_ = (call); say( "%s = %d\n", #call, (int)r_ ); if (r_ != VK_SUCCESS) goto done; } while (0)

int main(void)
{
    LARGE_INTEGER frequency, t0, t1;
    HMODULE vulkan;
    PFN_vkGetInstanceProcAddr gipa;
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice gpus[4];
    VkDevice device = VK_NULL_HANDLE;
    uint32_t count = 4, i;

    out = fopen( "C:\\orbis\\vkprobe64.txt", "w" );
    QueryPerformanceFrequency( &frequency );
    say( "vkprobe64: Vulkan from a Windows program\n" );
    if (!(vulkan = LoadLibraryA( "vulkan-1.dll" )))
    {
        say( "LoadLibrary vulkan-1.dll failed, error %lu\n", GetLastError() );
        goto done;
    }
    gipa = (PFN_vkGetInstanceProcAddr)GetProcAddress( vulkan, "vkGetInstanceProcAddr" );
    say( "vulkan-1.dll %p, vkGetInstanceProcAddr %p\n", vulkan, gipa );
    if (!gipa) goto done;

#define GLOBAL(name) PFN_##name name = (PFN_##name)gipa( NULL, #name )
    GLOBAL(vkCreateInstance);
    GLOBAL(vkEnumerateInstanceVersion);
    GLOBAL(vkEnumerateInstanceExtensionProperties);
    {
        uint32_t version = 0, extensions = 0;
        if (vkEnumerateInstanceVersion) vkEnumerateInstanceVersion( &version );
        if (vkEnumerateInstanceExtensionProperties) vkEnumerateInstanceExtensionProperties( NULL, &extensions, NULL );
        say( "instance version %u.%u.%u, %u instance extensions\n", VK_API_VERSION_MAJOR(version),
             VK_API_VERSION_MINOR(version), VK_API_VERSION_PATCH(version), extensions );
    }
    {
        VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .pApplicationName = "vkprobe64",
                                 .apiVersion = VK_API_VERSION_1_1};
        VkInstanceCreateInfo info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
        QueryPerformanceCounter( &t0 );
        CHECK( vkCreateInstance( &info, NULL, &instance ) );
        QueryPerformanceCounter( &t1 );
        say( "vkCreateInstance took %lld us\n", (t1.QuadPart - t0.QuadPart) * 1000000 / frequency.QuadPart );
    }
#define INSTANCE(name) PFN_##name name = (PFN_##name)gipa( instance, #name )
    INSTANCE(vkEnumeratePhysicalDevices);
    INSTANCE(vkGetPhysicalDeviceProperties);
    INSTANCE(vkGetPhysicalDeviceMemoryProperties);
    INSTANCE(vkCreateDevice);
    INSTANCE(vkGetDeviceProcAddr);
    CHECK( vkEnumeratePhysicalDevices( instance, &count, gpus ) );
    for (i = 0; i < count; i++)
    {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties( gpus[i], &props );
        say( "GPU %u: %s, Vulkan %u.%u.%u, vendor %#x, device %#x, type %u\n", i, props.deviceName,
             VK_API_VERSION_MAJOR(props.apiVersion), VK_API_VERSION_MINOR(props.apiVersion),
             VK_API_VERSION_PATCH(props.apiVersion), props.vendorID, props.deviceID, props.deviceType );
    }
    if (!count) goto done;
    {
        float priority = 1.0f;
        VkDeviceQueueCreateInfo queue = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, .queueFamilyIndex = 0,
                                         .queueCount = 1, .pQueuePriorities = &priority};
        VkDeviceCreateInfo info = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .queueCreateInfoCount = 1,
                                   .pQueueCreateInfos = &queue};
        CHECK( vkCreateDevice( gpus[0], &info, NULL, &device ) );
    }
#define DEVICE(name) PFN_##name name = (PFN_##name)vkGetDeviceProcAddr( device, #name )
    DEVICE(vkGetDeviceQueue);
    DEVICE(vkCreateBuffer);
    DEVICE(vkGetBufferMemoryRequirements);
    DEVICE(vkAllocateMemory);
    DEVICE(vkBindBufferMemory);
    DEVICE(vkMapMemory);
    DEVICE(vkCreateCommandPool);
    DEVICE(vkAllocateCommandBuffers);
    DEVICE(vkBeginCommandBuffer);
    DEVICE(vkCmdFillBuffer);
    DEVICE(vkEndCommandBuffer);
    DEVICE(vkCreateFence);
    DEVICE(vkResetFences);
    DEVICE(vkQueueSubmit);
    DEVICE(vkWaitForFences);
    {
        const VkDeviceSize size = 1 << 20;
        VkQueue queue;
        VkBuffer buffer;
        VkMemoryRequirements req;
        VkPhysicalDeviceMemoryProperties mem;
        VkDeviceMemory memory;
        VkCommandPool pool;
        VkCommandBuffer cmd;
        VkFence fence;
        uint32_t *data = NULL, type = ~0u, round;
        VkBufferCreateInfo binfo = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = size,
                                    .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
        VkCommandPoolCreateInfo pinfo = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                         .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT};
        VkFenceCreateInfo finfo = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};

        vkGetDeviceQueue( device, 0, 0, &queue );
        CHECK( vkCreateBuffer( device, &binfo, NULL, &buffer ) );
        vkGetBufferMemoryRequirements( device, buffer, &req );
        vkGetPhysicalDeviceMemoryProperties( gpus[0], &mem );
        for (i = 0; i < mem.memoryTypeCount && type == ~0u; i++)
            if ((req.memoryTypeBits & (1u << i)) &&
                (mem.memoryTypes[i].propertyFlags & (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) ==
                (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT))
                type = i;
        say( "memory type %u\n", type );
        {
            VkMemoryAllocateInfo ainfo = {.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .allocationSize = req.size,
                                          .memoryTypeIndex = type};
            CHECK( vkAllocateMemory( device, &ainfo, NULL, &memory ) );
        }
        CHECK( vkBindBufferMemory( device, buffer, memory, 0 ) );
        CHECK( vkMapMemory( device, memory, 0, size, 0, (void **)&data ) );
        say( "buffer mapped at %p\n", data );
        CHECK( vkCreateCommandPool( device, &pinfo, NULL, &pool ) );
        {
            VkCommandBufferAllocateInfo cinfo = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                                 .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
            CHECK( vkAllocateCommandBuffers( device, &cinfo, &cmd ) );
        }
        CHECK( vkCreateFence( device, &finfo, NULL, &fence ) );
        /* 100 rounds, each a GPU fill of a different value and a CPU check of both ends */
        QueryPerformanceCounter( &t0 );
        for (round = 0; round < 100; round++)
        {
            const uint32_t value = 0x12345600 + round;
            VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
            VkSubmitInfo submit = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cmd};
            VkResult r;

            if ((r = vkBeginCommandBuffer( cmd, &begin ))) { say( "round %u: begin %d\n", round, r ); goto done; }
            vkCmdFillBuffer( cmd, buffer, 0, size, value );
            if ((r = vkEndCommandBuffer( cmd ))) { say( "round %u: end %d\n", round, r ); goto done; }
            if ((r = vkQueueSubmit( queue, 1, &submit, fence ))) { say( "round %u: submit %d\n", round, r ); goto done; }
            if ((r = vkWaitForFences( device, 1, &fence, VK_TRUE, 5000000000ull ))) { say( "round %u: wait %d\n", round, r ); goto done; }
            vkResetFences( device, 1, &fence );
            if (data[0] != value || data[size / 4 - 1] != value)
            {
                say( "round %u: read %#x and %#x, expected %#x\n", round, data[0], data[size / 4 - 1], value );
                goto done;
            }
        }
        QueryPerformanceCounter( &t1 );
        say( "100 GPU fills of 1 MiB checked by the CPU: last %#x, %lld us per fill\n", data[0],
             (t1.QuadPart - t0.QuadPart) * 10000 / frequency.QuadPart );
        say( "vkprobe64: PASSED\n" );
    }
done:
    say( "vkprobe64: end\n" );
    if (out) fclose( out );
    return 0;
}
