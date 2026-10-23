"""Protect saved API credentials with Windows DPAPI; never use plaintext fallback."""

import base64
import os

from .common import BridgeError


def _crypt(data, encrypt):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptProtectData if encrypt else library.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise BridgeError('Windows could not protect or unlock this saved API key. Re-enter it in Connections.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def seal(secret):
    if not secret or os.name != 'nt':
        return None
    return {'type': 'windows-dpapi', 'data': base64.b64encode(_crypt(secret.encode(), True)).decode()}


def unlock(record):
    if not record:
        return ''
    if os.name != 'nt' or not isinstance(record, dict) or record.get('type') != 'windows-dpapi':
        raise BridgeError('This saved key belongs to a Windows account. Re-enter the key on this computer.')
    try:
        return _crypt(base64.b64decode(record['data'], validate=True), False).decode()
    except (KeyError, ValueError, UnicodeError):
        raise BridgeError('The saved key is invalid. Re-enter it in Connections.') from None
