#!/usr/bin/env python3
"""unoq_gpu_render.py - force one real GPU submission on the UNO Q.

Runs ON THE BOARD.  Usage:  python3 unoq_gpu_render.py [seconds]

The 11ae diff needs a Debian capture taken while the command processor is
actually running a job, not merely while the power domain is resumed:
forcing 5900000.gpu to power/control=on brings up the clocks and the GDSCs
but leaves CP_SQE_CNTL reading 0, because the reference driver starts the
processor on the first submission, not on resume.

There is no kmscube, modetest or glmark2 on this image and no compiler, so
the submission is made through the EGL surfaceless platform with ctypes:
an off-screen renderbuffer, a clear, and a glFinish, which is a genuine
freedreno command stream through the ring.

It renders in a loop for `seconds` (default 20) so that a capture taken
from another shell lands while the ring is busy.
"""
import ctypes
import sys
import time

EGL_SUCCESS = 0x3000
EGL_NO_DISPLAY = ctypes.c_void_p(0)
EGL_NO_CONTEXT = ctypes.c_void_p(0)
EGL_NO_SURFACE = ctypes.c_void_p(0)
EGL_PLATFORM_SURFACELESS_MESA = 0x31DD
EGL_OPENGL_ES_API = 0x30A0
EGL_SURFACE_TYPE = 0x3033
EGL_PBUFFER_BIT = 0x0001
EGL_RENDERABLE_TYPE = 0x3040
EGL_OPENGL_ES2_BIT = 0x0004
EGL_RED_SIZE, EGL_GREEN_SIZE, EGL_BLUE_SIZE = 0x3024, 0x3023, 0x3022
EGL_NONE = 0x3038
EGL_CONTEXT_CLIENT_VERSION = 0x3098

GL_COLOR_BUFFER_BIT = 0x4000
GL_FRAMEBUFFER = 0x8D40
GL_RENDERBUFFER = 0x8D41
GL_COLOR_ATTACHMENT0 = 0x8CE0
GL_RGBA8 = 0x8058
GL_RGBA = 0x1908
GL_UNSIGNED_BYTE = 0x1401
GL_FRAMEBUFFER_COMPLETE = 0x8CD5


def main() -> int:
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0

    egl = ctypes.CDLL("libEGL.so.1")
    gl = ctypes.CDLL("libGLESv2.so.2")

    egl.eglGetProcAddress.restype = ctypes.c_void_p
    egl.eglGetPlatformDisplay.restype = ctypes.c_void_p
    egl.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p,
                                          ctypes.c_void_p]
    egl.eglCreateContext.restype = ctypes.c_void_p
    egl.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_void_p, ctypes.c_void_p]
    egl.eglMakeCurrent.argtypes = [ctypes.c_void_p] * 4

    dpy = egl.eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, None, None)
    if not dpy:
        print("eglGetPlatformDisplay failed: 0x%X" % egl.eglGetError())
        return 1
    major, minor = ctypes.c_int(), ctypes.c_int()
    if not egl.eglInitialize(ctypes.c_void_p(dpy), ctypes.byref(major),
                             ctypes.byref(minor)):
        print("eglInitialize failed: 0x%X" % egl.eglGetError())
        return 1
    egl.eglQueryString.restype = ctypes.c_char_p
    print("EGL %d.%d  vendor=%s" % (major.value, minor.value,
                                    egl.eglQueryString(ctypes.c_void_p(dpy), 0x3053)))

    egl.eglBindAPI(EGL_OPENGL_ES_API)
    attribs = (ctypes.c_int * 11)(
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
        EGL_NONE)
    cfg = ctypes.c_void_p()
    n = ctypes.c_int()
    if not egl.eglChooseConfig(ctypes.c_void_p(dpy), attribs,
                               ctypes.byref(cfg), 1, ctypes.byref(n)) or not n.value:
        print("eglChooseConfig failed: 0x%X" % egl.eglGetError())
        return 1

    ctx_attr = (ctypes.c_int * 3)(EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE)
    ctx = egl.eglCreateContext(ctypes.c_void_p(dpy), cfg, None, ctx_attr)
    if not ctx:
        print("eglCreateContext failed: 0x%X" % egl.eglGetError())
        return 1
    if not egl.eglMakeCurrent(ctypes.c_void_p(dpy), EGL_NO_SURFACE,
                              EGL_NO_SURFACE, ctypes.c_void_p(ctx)):
        print("eglMakeCurrent failed: 0x%X" % egl.eglGetError())
        return 1

    gl.glGetString.restype = ctypes.c_char_p
    print("GL_RENDERER = %s" % gl.glGetString(0x1F01))
    print("GL_VERSION  = %s" % gl.glGetString(0x1F02))

    rb, fb = ctypes.c_uint(), ctypes.c_uint()
    gl.glGenRenderbuffers(1, ctypes.byref(rb))
    gl.glBindRenderbuffer(GL_RENDERBUFFER, rb)
    gl.glRenderbufferStorage(GL_RENDERBUFFER, GL_RGBA8, 512, 512)
    gl.glGenFramebuffers(1, ctypes.byref(fb))
    gl.glBindFramebuffer(GL_FRAMEBUFFER, fb)
    gl.glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                                 GL_RENDERBUFFER, rb)
    st = gl.glCheckFramebufferStatus(GL_FRAMEBUFFER)
    if st != GL_FRAMEBUFFER_COMPLETE:
        print("framebuffer incomplete: 0x%X" % st)
        return 1
    gl.glViewport(0, 0, 512, 512)

    px = (ctypes.c_ubyte * 4)()
    frames = 0
    gl.glClearColor.argtypes = [ctypes.c_float] * 4
    end = time.time() + secs
    while time.time() < end:
        c = (frames % 64) / 64.0
        gl.glClearColor(ctypes.c_float(c), ctypes.c_float(1.0 - c),
                        ctypes.c_float(0.25), ctypes.c_float(1.0))
        gl.glClear(GL_COLOR_BUFFER_BIT)
        gl.glFinish()
        frames += 1
    gl.glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px)
    print("frames=%d  last pixel = %02X %02X %02X %02X"
          % (frames, px[0], px[1], px[2], px[3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
