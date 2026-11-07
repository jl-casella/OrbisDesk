/* SPDX-License-Identifier: LGPL-2.1-or-later
 * W091: what the Khronos loader (vulkan-1.dll) sees for layers on the PS4. MangoHud's layer
 * DLL loads but no overlay shows (W088-W090), and the loader's own log does not reach the run
 * log. This writes to C:\orbis\vklayers64.txt: the environment the loader reads, the
 * instance layers it lists, and every loader message during two vkCreateInstance calls
 * (implicit layers only, then with MangoHud's layer named explicitly), through a
 * VK_EXT_debug_utils messenger in the create info. */
#include <windows.h>
#include <stdio.h>
#include <vulkan/vulkan_core.h>

static FILE *out;

static VKAPI_ATTR VkBool32 VKAPI_CALL messenger( VkDebugUtilsMessageSeverityFlagBitsEXT severity,
                                                 VkDebugUtilsMessageTypeFlagsEXT type,
                                                 const VkDebugUtilsMessengerCallbackDataEXT *data, void *user )
{
    fprintf( out, "  [%#x] %s\n", (unsigned)severity, data->pMessage );
    fflush( out );
    return VK_FALSE;
}

static void create( PFN_vkGetInstanceProcAddr gipa, const char *layer )
{
    PFN_vkCreateInstance create_instance = (PFN_vkCreateInstance)gipa( NULL, "vkCreateInstance" );
    const char *extensions[] = {VK_EXT_DEBUG_UTILS_EXTENSION_NAME};
    VkDebugUtilsMessengerCreateInfoEXT debug = {.sType = VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT,
                                                .messageSeverity = 0x1111, .messageType = 0xf,
                                                .pfnUserCallback = messenger};
    VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .pApplicationName = "vklayers64",
                             .apiVersion = VK_API_VERSION_1_1};
    VkInstanceCreateInfo info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pNext = &debug,
                                 .pApplicationInfo = &app, .enabledExtensionCount = 1,
                                 .ppEnabledExtensionNames = extensions, .enabledLayerCount = layer ? 1 : 0,
                                 .ppEnabledLayerNames = &layer};
    VkInstance instance = VK_NULL_HANDLE;
    VkResult result;

    fprintf( out, "vkCreateInstance with %s:\n", layer ? layer : "implicit layers only" );
    fflush( out );
    result = create_instance( &info, NULL, &instance );
    fprintf( out, "  = %d\n", (int)result );
    if (!result)
    {
        PFN_vkDestroyInstance destroy = (PFN_vkDestroyInstance)gipa( instance, "vkDestroyInstance" );
        destroy( instance, NULL );
    }
    fflush( out );
}

int main( void )
{
    static const char *variables[] = {"MANGOHUD", "VK_DRIVER_FILES", "VK_ADD_IMPLICIT_LAYER_PATH",
                                      "VK_LOADER_LAYERS_ENABLE", "VK_LOADER_DEBUG", "APPDATA", "WINE_D3D_CONFIG"};
    VkLayerProperties layers[32];
    uint32_t count = 32, i;
    char value[512];
    HMODULE vulkan;
    PFN_vkGetInstanceProcAddr gipa;

    out = fopen( "C:\\orbis\\vklayers64.txt", "w" );
    for (i = 0; i < sizeof(variables) / sizeof(variables[0]); i++)
    {
        DWORD length = GetEnvironmentVariableA( variables[i], value, sizeof(value) );
        fprintf( out, "%s=%s\n", variables[i], length ? value : "(unset)" );
    }
    vulkan = LoadLibraryA( "vulkan-1.dll" );
    GetModuleFileNameA( vulkan, value, sizeof(value) );
    fprintf( out, "vulkan-1.dll %p from %s\n", vulkan, vulkan ? value : "-" );
    if (!vulkan) return 1;
    gipa = (PFN_vkGetInstanceProcAddr)GetProcAddress( vulkan, "vkGetInstanceProcAddr" );
    {
        PFN_vkEnumerateInstanceLayerProperties enumerate =
            (PFN_vkEnumerateInstanceLayerProperties)gipa( NULL, "vkEnumerateInstanceLayerProperties" );
        VkResult result = enumerate( &count, layers );
        fprintf( out, "vkEnumerateInstanceLayerProperties = %d, %u layers\n", (int)result, count );
        for (i = 0; i < count; i++)
            fprintf( out, "  %s (spec %u.%u, impl %u): %s\n", layers[i].layerName, VK_API_VERSION_MAJOR(layers[i].specVersion),
                     VK_API_VERSION_MINOR(layers[i].specVersion), layers[i].implementationVersion, layers[i].description );
    }
    fflush( out );
    create( gipa, NULL );
    create( gipa, "VK_LAYER_MANGOHUD_overlay_x86_64" );
    {
        HMODULE mangohud = GetModuleHandleA( "libMangoHud.dll" );
        fprintf( out, "libMangoHud.dll loaded: %p\n", mangohud );
    }
    fprintf( out, "vklayers64: end\n" );
    fclose( out );
    return 0;
}
