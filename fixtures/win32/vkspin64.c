/* SPDX-License-Identifier: LGPL-2.1-or-later
 * W072 (H3): a Windows program that draws with Vulkan into its own window through a
 * VK_KHR_win32_surface swapchain: the spinning triangle of the G001 probe
 * (native/vk_probe/shaders), resized with the window. The frame rate is shown in the title
 * once a second and written to C:\orbis\vkspin64.txt. Each failing Vulkan call is written
 * there and ends the program. */
#define VK_USE_PLATFORM_WIN32_KHR
#include <windows.h>
#include <math.h>
#include <stdio.h>
#include <vulkan/vulkan.h>
#include "../../native/vk_probe/shaders/triangle_vert.h"
#include "../../native/vk_probe/shaders/triangle_frag.h"

static FILE *out;
static BOOL resized, closing;

static void say( const char *format, ... )
{
    va_list args;
    if (!out) return;
    va_start( args, format );
    vfprintf( out, format, args );
    va_end( args );
    fflush( out );
}

#define CHECK(call) do { VkResult r_ = (call); if (r_ != VK_SUCCESS) { say( "%s = %d\n", #call, (int)r_ ); goto done; } } while (0)

static LRESULT CALLBACK window_proc( HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam )
{
    switch (msg)
    {
    case WM_SIZE: resized = TRUE; break;
    case WM_CLOSE: closing = TRUE; DestroyWindow( hwnd ); return 0;
    case WM_DESTROY: PostQuitMessage( 0 ); return 0;
    case WM_PAINT: ValidateRect( hwnd, NULL ); return 0;
    case WM_ERASEBKGND: return 1;
    }
    return DefWindowProcW( hwnd, msg, wparam, lparam );
}

enum { MAX_IMAGES = 8 };
static VkDevice device;
static VkSwapchainKHR swapchain;
static VkImageView views[MAX_IMAGES];
static VkFramebuffer framebuffers[MAX_IMAGES];
static uint32_t image_count;
static VkExtent2D extent;

int WINAPI WinMain( HINSTANCE instance_handle, HINSTANCE previous, LPSTR command_line, int show )
{
    WNDCLASSW wc = {0};
    HWND hwnd;
    VkInstance instance = VK_NULL_HANDLE;
    VkSurfaceKHR surface;
    VkPhysicalDevice gpu;
    VkQueue queue;
    VkRenderPass pass;
    VkPipelineLayout layout;
    VkPipeline pipeline;
    VkCommandPool pool;
    VkCommandBuffer cmd;
    VkSemaphore acquired, rendered;
    VkFence fence;
    VkSurfaceFormatKHR format;
    LARGE_INTEGER frequency, start, now, second_start;
    unsigned int frames = 0, second_frames = 0, i, count = 1;
    float angle = 0;

    out = fopen( "C:\\orbis\\vkspin64.txt", "w" );
    QueryPerformanceFrequency( &frequency );
    wc.lpfnWndProc = window_proc;
    wc.hInstance = instance_handle;
    wc.hCursor = LoadCursorW( NULL, (LPCWSTR)IDC_ARROW );
    wc.lpszClassName = L"vkspin64";
    RegisterClassW( &wc );
    hwnd = CreateWindowW( L"vkspin64", L"vkspin64 - Vulkan", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 80, 60, 640, 480,
                          NULL, NULL, instance_handle, NULL );
    say( "window %p\n", hwnd );

    {
        const char *extensions[] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_WIN32_SURFACE_EXTENSION_NAME};
        VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .pApplicationName = "vkspin64",
                                 .apiVersion = VK_API_VERSION_1_1};
        VkInstanceCreateInfo info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app,
                                     .enabledExtensionCount = 2, .ppEnabledExtensionNames = extensions};
        CHECK( vkCreateInstance( &info, NULL, &instance ) );
    }
    {
        VkWin32SurfaceCreateInfoKHR info = {.sType = VK_STRUCTURE_TYPE_WIN32_SURFACE_CREATE_INFO_KHR,
                                            .hinstance = instance_handle, .hwnd = hwnd};
        CHECK( vkCreateWin32SurfaceKHR( instance, &info, NULL, &surface ) );
    }
    CHECK( vkEnumeratePhysicalDevices( instance, &count, &gpu ) );
    {
        VkBool32 supported = VK_FALSE;
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties( gpu, &props );
        vkGetPhysicalDeviceSurfaceSupportKHR( gpu, 0, surface, &supported );
        say( "GPU %s, presentation support %u\n", props.deviceName, supported );
    }
    {
        const char *extensions[] = {VK_KHR_SWAPCHAIN_EXTENSION_NAME};
        float priority = 1.0f;
        VkDeviceQueueCreateInfo queue_info = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, .queueCount = 1,
                                              .pQueuePriorities = &priority};
        VkDeviceCreateInfo info = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .queueCreateInfoCount = 1,
                                   .pQueueCreateInfos = &queue_info, .enabledExtensionCount = 1,
                                   .ppEnabledExtensionNames = extensions};
        CHECK( vkCreateDevice( gpu, &info, NULL, &device ) );
    }
    vkGetDeviceQueue( device, 0, 0, &queue );
    {
        VkSurfaceFormatKHR formats[16];
        uint32_t format_count = 16;
        CHECK( vkGetPhysicalDeviceSurfaceFormatsKHR( gpu, surface, &format_count, formats ) );
        format = formats[0];
        for (i = 0; i < format_count; i++)
            if (formats[i].format == VK_FORMAT_B8G8R8A8_UNORM) format = formats[i];
        say( "%u surface formats, using %d\n", format_count, format.format );
    }
    {
        VkAttachmentDescription attachment = {.format = format.format, .samples = VK_SAMPLE_COUNT_1_BIT,
                                              .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR, .storeOp = VK_ATTACHMENT_STORE_OP_STORE,
                                              .stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE,
                                              .stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE,
                                              .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
                                              .finalLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR};
        VkAttachmentReference reference = {0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
        VkSubpassDescription subpass = {.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS, .colorAttachmentCount = 1,
                                        .pColorAttachments = &reference};
        VkRenderPassCreateInfo info = {.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO, .attachmentCount = 1,
                                       .pAttachments = &attachment, .subpassCount = 1, .pSubpasses = &subpass};
        CHECK( vkCreateRenderPass( device, &info, NULL, &pass ) );
    }
    {
        VkShaderModule vs, fs;
        VkShaderModuleCreateInfo vinfo = {.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
                                          .codeSize = sizeof(triangle_vert), .pCode = triangle_vert};
        VkShaderModuleCreateInfo finfo = {.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
                                          .codeSize = sizeof(triangle_frag), .pCode = triangle_frag};
        VkPushConstantRange push = {VK_SHADER_STAGE_VERTEX_BIT, 0, 2 * sizeof(float)};
        VkPipelineLayoutCreateInfo linfo = {.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
                                            .pushConstantRangeCount = 1, .pPushConstantRanges = &push};
        VkPipelineShaderStageCreateInfo stages[2] = {
            {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_VERTEX_BIT, .pName = "main"},
            {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_FRAGMENT_BIT, .pName = "main"}};
        VkPipelineVertexInputStateCreateInfo vertex = {.sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
        VkPipelineInputAssemblyStateCreateInfo assembly = {.sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
                                                           .topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST};
        VkPipelineViewportStateCreateInfo viewport = {.sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
                                                      .viewportCount = 1, .scissorCount = 1};
        VkPipelineRasterizationStateCreateInfo raster = {.sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
                                                         .polygonMode = VK_POLYGON_MODE_FILL, .cullMode = VK_CULL_MODE_NONE,
                                                         .lineWidth = 1.0f};
        VkPipelineMultisampleStateCreateInfo multisample = {.sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
                                                            .rasterizationSamples = VK_SAMPLE_COUNT_1_BIT};
        VkPipelineColorBlendAttachmentState blend_attachment = {.colorWriteMask = 0xf};
        VkPipelineColorBlendStateCreateInfo blend = {.sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
                                                     .attachmentCount = 1, .pAttachments = &blend_attachment};
        VkDynamicState dynamic_states[2] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
        VkPipelineDynamicStateCreateInfo dynamic = {.sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO,
                                                    .dynamicStateCount = 2, .pDynamicStates = dynamic_states};
        VkGraphicsPipelineCreateInfo info = {.sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO, .stageCount = 2,
                                             .pStages = stages, .pVertexInputState = &vertex, .pInputAssemblyState = &assembly,
                                             .pViewportState = &viewport, .pRasterizationState = &raster,
                                             .pMultisampleState = &multisample, .pColorBlendState = &blend,
                                             .pDynamicState = &dynamic, .renderPass = pass};
        CHECK( vkCreateShaderModule( device, &vinfo, NULL, &vs ) );
        CHECK( vkCreateShaderModule( device, &finfo, NULL, &fs ) );
        stages[0].module = vs;
        stages[1].module = fs;
        CHECK( vkCreatePipelineLayout( device, &linfo, NULL, &layout ) );
        info.layout = layout;
        CHECK( vkCreateGraphicsPipelines( device, VK_NULL_HANDLE, 1, &info, NULL, &pipeline ) );
    }
    {
        VkCommandPoolCreateInfo pinfo = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                         .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT};
        VkCommandBufferAllocateInfo cinfo = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
                                             .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
        VkSemaphoreCreateInfo sinfo = {.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
        VkFenceCreateInfo finfo = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO, .flags = VK_FENCE_CREATE_SIGNALED_BIT};
        CHECK( vkCreateCommandPool( device, &pinfo, NULL, &pool ) );
        cinfo.commandPool = pool;
        CHECK( vkAllocateCommandBuffers( device, &cinfo, &cmd ) );
        CHECK( vkCreateSemaphore( device, &sinfo, NULL, &acquired ) );
        CHECK( vkCreateSemaphore( device, &sinfo, NULL, &rendered ) );
        CHECK( vkCreateFence( device, &finfo, NULL, &fence ) );
    }

    resized = TRUE;
    QueryPerformanceCounter( &start );
    second_start = start;
    while (!closing)
    {
        MSG msg;
        uint32_t index;
        VkResult r;

        while (PeekMessageW( &msg, NULL, 0, 0, PM_REMOVE ))
        {
            if (msg.message == WM_QUIT) closing = TRUE;
            TranslateMessage( &msg );
            DispatchMessageW( &msg );
        }
        if (closing) break;

        if (resized)
        {
            /* (re)create the swapchain at the window's size */
            VkSurfaceCapabilitiesKHR caps;
            VkSwapchainKHR old = swapchain;
            VkImage images[MAX_IMAGES];
            resized = FALSE;
            CHECK( vkDeviceWaitIdle( device ) );
            CHECK( vkGetPhysicalDeviceSurfaceCapabilitiesKHR( gpu, surface, &caps ) );
            extent = caps.currentExtent;
            if (extent.width == 0xffffffff)
            {
                RECT rect;
                GetClientRect( hwnd, &rect );
                extent.width = rect.right - rect.left;
                extent.height = rect.bottom - rect.top;
            }
            if (!extent.width || !extent.height) { Sleep( 10 ); resized = TRUE; continue; }
            {
                VkSwapchainCreateInfoKHR info = {.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR, .surface = surface,
                                                 .minImageCount = caps.minImageCount < 2 ? 2 : caps.minImageCount,
                                                 .imageFormat = format.format, .imageColorSpace = format.colorSpace,
                                                 .imageExtent = extent, .imageArrayLayers = 1,
                                                 .imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,
                                                 .preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR,
                                                 .compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,
                                                 .presentMode = VK_PRESENT_MODE_FIFO_KHR, .clipped = VK_TRUE,
                                                 .oldSwapchain = old};
                if (info.minImageCount > MAX_IMAGES) info.minImageCount = MAX_IMAGES;
                CHECK( vkCreateSwapchainKHR( device, &info, NULL, &swapchain ) );
            }
            for (i = 0; i < image_count; i++)
            {
                vkDestroyFramebuffer( device, framebuffers[i], NULL );
                vkDestroyImageView( device, views[i], NULL );
            }
            if (old) vkDestroySwapchainKHR( device, old, NULL );
            image_count = MAX_IMAGES;
            CHECK( vkGetSwapchainImagesKHR( device, swapchain, &image_count, images ) );
            for (i = 0; i < image_count; i++)
            {
                VkImageViewCreateInfo vinfo = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = images[i],
                                               .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = format.format,
                                               .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
                VkFramebufferCreateInfo finfo = {.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO, .renderPass = pass,
                                                 .attachmentCount = 1, .pAttachments = &views[i], .width = extent.width,
                                                 .height = extent.height, .layers = 1};
                CHECK( vkCreateImageView( device, &vinfo, NULL, &views[i] ) );
                CHECK( vkCreateFramebuffer( device, &finfo, NULL, &framebuffers[i] ) );
            }
            say( "swapchain %ux%u, %u images\n", extent.width, extent.height, image_count );
        }

        CHECK( vkWaitForFences( device, 1, &fence, VK_TRUE, UINT64_MAX ) );
        r = vkAcquireNextImageKHR( device, swapchain, UINT64_MAX, acquired, VK_NULL_HANDLE, &index );
        if (r == VK_ERROR_OUT_OF_DATE_KHR) { resized = TRUE; continue; }
        if (r != VK_SUCCESS && r != VK_SUBOPTIMAL_KHR) { say( "vkAcquireNextImageKHR = %d\n", r ); break; }
        CHECK( vkResetFences( device, 1, &fence ) );
        {
            VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                              .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
            VkClearValue clear = {.color = {{0.05f, 0.05f, 0.15f + 0.1f * sinf( angle ), 1.0f}}};
            VkRenderPassBeginInfo rp = {.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO, .renderPass = pass,
                                        .framebuffer = framebuffers[index], .renderArea = {{0, 0}, extent},
                                        .clearValueCount = 1, .pClearValues = &clear};
            VkViewport viewport = {0, 0, extent.width, extent.height, 0, 1};
            VkRect2D scissor = {{0, 0}, extent};
            float push[2] = {angle, (float)extent.height / extent.width};
            CHECK( vkResetCommandBuffer( cmd, 0 ) );
            CHECK( vkBeginCommandBuffer( cmd, &begin ) );
            vkCmdBeginRenderPass( cmd, &rp, VK_SUBPASS_CONTENTS_INLINE );
            vkCmdBindPipeline( cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline );
            vkCmdSetViewport( cmd, 0, 1, &viewport );
            vkCmdSetScissor( cmd, 0, 1, &scissor );
            vkCmdPushConstants( cmd, layout, VK_SHADER_STAGE_VERTEX_BIT, 0, sizeof(push), push );
            vkCmdDraw( cmd, 3, 1, 0, 0 );
            vkCmdEndRenderPass( cmd );
            CHECK( vkEndCommandBuffer( cmd ) );
        }
        {
            VkPipelineStageFlags stage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
            VkSubmitInfo submit = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .waitSemaphoreCount = 1,
                                   .pWaitSemaphores = &acquired, .pWaitDstStageMask = &stage, .commandBufferCount = 1,
                                   .pCommandBuffers = &cmd, .signalSemaphoreCount = 1, .pSignalSemaphores = &rendered};
            VkPresentInfoKHR present = {.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR, .waitSemaphoreCount = 1,
                                        .pWaitSemaphores = &rendered, .swapchainCount = 1, .pSwapchains = &swapchain,
                                        .pImageIndices = &index};
            CHECK( vkQueueSubmit( queue, 1, &submit, fence ) );
            r = vkQueuePresentKHR( queue, &present );
            if (r == VK_ERROR_OUT_OF_DATE_KHR || r == VK_SUBOPTIMAL_KHR) resized = TRUE;
            else if (r != VK_SUCCESS) { say( "vkQueuePresentKHR = %d\n", r ); break; }
        }

        frames++;
        second_frames++;
        QueryPerformanceCounter( &now );
        angle = (float)(now.QuadPart - start.QuadPart) / frequency.QuadPart * 1.5f;
        if (now.QuadPart - second_start.QuadPart >= frequency.QuadPart)
        {
            double seconds = (double)(now.QuadPart - second_start.QuadPart) / frequency.QuadPart;
            WCHAR title[96];
            swprintf( title, ARRAYSIZE(title), L"vkspin64 - Vulkan - %.1f FPS (%ux%u)", second_frames / seconds,
                      extent.width, extent.height );
            SetWindowTextW( hwnd, title );
            say( "fps %.1f, %u frames, %ux%u\n", second_frames / seconds, frames, extent.width, extent.height );
            second_frames = 0;
            second_start = now;
        }
    }
done:
    say( "vkspin64: end after %u frames\n", frames );
    if (device) vkDeviceWaitIdle( device );
    if (out) fclose( out );
    return 0;
}
