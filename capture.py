"""화면의 한 부분만 빠르게 캡처 (GDI BitBlt · ctypes)

PIL ImageGrab(all_screens=True)은 모니터가 여러 대면 전체 화면(예: 9840×3840)을 통째로 뜬 뒤 잘라서 한 번에 0.4초쯤 걸림 →
필요한 네모만 바로 복사하면 몇 ms. 화면에 보이는 그대로를 복사할 뿐, 게임 프로세스에는 접근하지 않음.
"""
import ctypes, ctypes.wintypes as W
from PIL import Image

u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
u32.GetDC.restype = W.HDC; u32.GetDC.argtypes = [W.HWND]
u32.ReleaseDC.argtypes = [W.HWND, W.HDC]
g32.CreateCompatibleDC.restype = W.HDC; g32.CreateCompatibleDC.argtypes = [W.HDC]
g32.CreateCompatibleBitmap.restype = W.HBITMAP; g32.CreateCompatibleBitmap.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int]
g32.SelectObject.restype = W.HGDIOBJ; g32.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
g32.BitBlt.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HDC, ctypes.c_int, ctypes.c_int, W.DWORD]
g32.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, ctypes.c_void_p, ctypes.c_void_p, W.UINT]
g32.DeleteObject.argtypes = [W.HGDIOBJ]; g32.DeleteDC.argtypes = [W.HDC]
SRCCOPY = 0x00CC0020


class BMI(ctypes.Structure):
    _fields_ = [('biSize', W.DWORD), ('biWidth', W.LONG), ('biHeight', W.LONG), ('biPlanes', W.WORD), ('biBitCount', W.WORD), ('biCompression', W.DWORD),
                ('biSizeImage', W.DWORD), ('biXPelsPerMeter', W.LONG), ('biYPelsPerMeter', W.LONG), ('biClrUsed', W.DWORD), ('biClrImportant', W.DWORD)]


def grab(box):
    """box = (왼쪽, 위, 오른쪽, 아래) 화면 좌표 → PIL RGB 그림"""
    x0, y0, x1, y1 = (int(v) for v in box); w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        raise ValueError('empty box')
    sdc = u32.GetDC(None); mdc = g32.CreateCompatibleDC(sdc); bmp = g32.CreateCompatibleBitmap(sdc, w, h); old = g32.SelectObject(mdc, bmp)
    try:
        if not g32.BitBlt(mdc, 0, 0, w, h, sdc, x0, y0, SRCCOPY):
            raise OSError('BitBlt failed')
        bi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0); buf = ctypes.create_string_buffer(w * h * 4)
        g32.SelectObject(mdc, old)
        if not g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0):
            raise OSError('GetDIBits failed')
        return Image.frombuffer('RGB', (w, h), buf, 'raw', 'BGRX', 0, 1)
    finally:
        g32.DeleteObject(bmp); g32.DeleteDC(mdc); u32.ReleaseDC(None, sdc)
