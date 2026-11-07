/* SPDX-License-Identifier: LGPL-2.1-or-later
 * W084: which kind of OpenGL drawing loses geometry through Zink on the PS4. glxgears
 * (W080-W083) lost parts of its gears from frame to frame, with a barrier between draws
 * (ZINK_DEBUG=sync) and without RADV's depth compression alike. This draws the same lit,
 * spinning ring (front face, back face and outer band, like a gear without teeth) six ways
 * at once, in a 3x2 grid; back faces are culled, as glxgears does, except in panel 6:
 *
 *   1 top left      immediate mode, GL_QUAD_STRIP, smooth shading, depth test
 *   2 top middle    immediate mode, GL_QUAD_STRIP, flat shading, depth test
 *   3 top right     immediate mode, GL_TRIANGLE_STRIP (same vertices), flat shading, depth test
 *   4 bottom left   display list (as glxgears), GL_QUAD_STRIP, flat shading, depth test
 *   5 bottom middle immediate mode, GL_QUADS, flat shading, depth test
 *   6 bottom right  immediate mode, GL_QUAD_STRIP, flat shading, depth test, no face culling
 *
 * The FPS goes to the title and to C:\orbis\gltest64.txt, with the GL strings. */
#include <windows.h>
#include <GL/gl.h>
#include <math.h>
#include <stdio.h>
#include <stdarg.h>

static FILE *out;
static BOOL done;
static GLuint ring_list;

static void note( const char *format, ... )
{
    va_list args;
    if (!out) out = fopen( "C:\\orbis\\gltest64.txt", "w" );
    if (!out) return;
    va_start( args, format );
    vfprintf( out, format, args );
    va_end( args );
    fflush( out );
}

enum { SEGMENTS = 40 };
static const float inner = 1.0f, outer = 2.6f, half_width = 0.4f;

static void point( float radius, int i, float z )
{
    float angle = i * 2.0f * (float)M_PI / SEGMENTS;
    glVertex3f( radius * cosf( angle ), radius * sinf( angle ), z );
}

static void outward_normal( int i )
{
    float angle = (i + 0.5f) * 2.0f * (float)M_PI / SEGMENTS;
    glNormal3f( cosf( angle ), sinf( angle ), 0.0f );
}

/* the ring with strips (mode GL_QUAD_STRIP or GL_TRIANGLE_STRIP: same vertex order) */
static void ring_strips( GLenum mode )
{
    int i;
    glNormal3f( 0, 0, 1 );
    glBegin( mode );
    for (i = 0; i <= SEGMENTS; i++) { point( inner, i, half_width ); point( outer, i, half_width ); }
    glEnd();
    glNormal3f( 0, 0, -1 );
    glBegin( mode );
    for (i = 0; i <= SEGMENTS; i++) { point( outer, i, -half_width ); point( inner, i, -half_width ); }
    glEnd();
    glBegin( mode );
    for (i = 0; i <= SEGMENTS; i++)
    {
        outward_normal( i );
        point( outer, i, half_width );
        point( outer, i, -half_width );
    }
    glEnd();
}

/* the same ring with separate quads */
static void ring_quads( void )
{
    int i;
    glBegin( GL_QUADS );
    for (i = 0; i < SEGMENTS; i++)
    {
        glNormal3f( 0, 0, 1 );
        point( inner, i, half_width ); point( outer, i, half_width );
        point( outer, i + 1, half_width ); point( inner, i + 1, half_width );
        glNormal3f( 0, 0, -1 );
        point( inner, i, -half_width ); point( inner, i + 1, -half_width );
        point( outer, i + 1, -half_width ); point( outer, i, -half_width );
        outward_normal( i );
        point( outer, i, half_width ); point( outer, i, -half_width );
        point( outer, i + 1, -half_width ); point( outer, i + 1, half_width );
    }
    glEnd();
}

static LRESULT CALLBACK window_proc( HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam )
{
    if (msg == WM_CLOSE) { done = TRUE; DestroyWindow( hwnd ); return 0; }
    if (msg == WM_DESTROY) { PostQuitMessage( 0 ); return 0; }
    return DefWindowProcA( hwnd, msg, wparam, lparam );
}

int main( void )
{
    static const float colors[6][4] = {{0.9f, 0.1f, 0.1f, 1}, {0.1f, 0.8f, 0.2f, 1}, {0.2f, 0.3f, 1.0f, 1},
                                       {0.9f, 0.8f, 0.1f, 1}, {0.8f, 0.2f, 0.9f, 1}, {0.1f, 0.8f, 0.9f, 1}};
    static const float light[4] = {5.0f, 5.0f, 10.0f, 0.0f};
    PIXELFORMATDESCRIPTOR pfd = {sizeof(pfd), 1, PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER,
                                 PFD_TYPE_RGBA, 24, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 24};
    WNDCLASSA wc = {CS_OWNDC, window_proc};
    LARGE_INTEGER frequency, start, now, second_start;
    unsigned int frames = 0;
    HWND hwnd;
    HDC hdc;
    HGLRC context;
    int format, panel;

    QueryPerformanceFrequency( &frequency );
    wc.hInstance = GetModuleHandleA( NULL );
    wc.hCursor = LoadCursorA( NULL, (LPCSTR)IDC_ARROW );
    wc.lpszClassName = "gltest64";
    RegisterClassA( &wc );
    hwnd = CreateWindowA( "gltest64", "gltest64", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 40, 30, 900, 640, NULL, NULL,
                          wc.hInstance, NULL );
    hdc = GetDC( hwnd );
    if (!(format = ChoosePixelFormat( hdc, &pfd )) || !SetPixelFormat( hdc, format, &pfd ) ||
        !(context = wglCreateContext( hdc )) || !wglMakeCurrent( hdc, context ))
    {
        note( "OpenGL setup failed: format %d, error %lu\n", format, GetLastError() );
        return 1;
    }
    note( "GL_RENDERER = %s\nGL_VERSION = %s\n", glGetString( GL_RENDERER ), glGetString( GL_VERSION ) );

    glLightfv( GL_LIGHT0, GL_POSITION, light );
    glEnable( GL_LIGHTING );
    glEnable( GL_LIGHT0 );
    glEnable( GL_CULL_FACE );
    glEnable( GL_NORMALIZE );
    ring_list = glGenLists( 1 );
    glNewList( ring_list, GL_COMPILE );
    ring_strips( GL_QUAD_STRIP );
    glEndList();

    QueryPerformanceCounter( &start );
    second_start = start;
    while (!done)
    {
        MSG msg;
        RECT rect;
        float angle, width, height;

        while (PeekMessageA( &msg, NULL, 0, 0, PM_REMOVE ))
        {
            if (msg.message == WM_QUIT) done = TRUE;
            TranslateMessage( &msg );
            DispatchMessageA( &msg );
        }
        if (done) break;
        GetClientRect( hwnd, &rect );
        width = (rect.right - rect.left) / 3.0f;
        height = (rect.bottom - rect.top) / 2.0f;
        QueryPerformanceCounter( &now );
        angle = (float)(now.QuadPart - start.QuadPart) / frequency.QuadPart * 60.0f;

        glViewport( 0, 0, rect.right - rect.left, rect.bottom - rect.top );
        glClearColor( 0.08f, 0.08f, 0.1f, 1 );
        glClear( GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT );
        for (panel = 0; panel < 6; panel++)
        {
            int column = panel % 3, row = panel / 3;
            glViewport( (GLint)(column * width), (GLint)((1 - row) * height), (GLsizei)width, (GLsizei)height );
            glMatrixMode( GL_PROJECTION );
            glLoadIdentity();
            glFrustum( -1.0, 1.0, -height / width, height / width, 5.0, 60.0 );
            glMatrixMode( GL_MODELVIEW );
            glLoadIdentity();
            glTranslatef( 0, 0, -12 );
            glRotatef( 20, 1, 0, 0 );
            glRotatef( 30, 0, 1, 0 );
            glRotatef( angle, 0, 0, 1 );
            glMaterialfv( GL_FRONT, GL_AMBIENT_AND_DIFFUSE, colors[panel] );
            glShadeModel( panel == 0 ? GL_SMOOTH : GL_FLAT );
            glEnable( GL_DEPTH_TEST );
            if (panel == 5) glDisable( GL_CULL_FACE ); else glEnable( GL_CULL_FACE );
            switch (panel)
            {
            case 0: case 1: case 5: ring_strips( GL_QUAD_STRIP ); break;
            case 2: ring_strips( GL_TRIANGLE_STRIP ); break;
            case 3: glCallList( ring_list ); break;
            case 4: ring_quads(); break;
            }
        }
        SwapBuffers( hdc );

        frames++;
        if (now.QuadPart - second_start.QuadPart >= frequency.QuadPart)
        {
            double seconds = (double)(now.QuadPart - second_start.QuadPart) / frequency.QuadPart;
            char title[64];
            snprintf( title, sizeof(title), "gltest64 - %.1f FPS", frames / seconds );
            SetWindowTextA( hwnd, title );
            note( "%.1f FPS\n", frames / seconds );
            frames = 0;
            second_start = now;
        }
    }
    note( "gltest64: end\n" );
    wglMakeCurrent( NULL, NULL );
    wglDeleteContext( context );
    return 0;
}
