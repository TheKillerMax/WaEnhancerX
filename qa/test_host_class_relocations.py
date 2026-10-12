#!/usr/bin/env python3
"""Statically validate known WhatsApp host class locations; no Android runtime required.

Usage: python3 qa/test_host_class_relocations.py /path/to/WhatsApp.apk
Do not commit proprietary WhatsApp APKs or DEX dumps.
"""
import argparse
import re
import struct
import zipfile


def uleb128(data, pos):
    value = 0
    for shift in range(0, 35, 7):
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 128:
            return pos, value
    raise ValueError("Invalid DEX uleb128")


def string_at(data, pos):
    pos, _ = uleb128(data, pos)
    end = data.index(b"\0", pos)
    return data[pos:end].decode("utf-8", errors="replace")


def defined_classes(apk_file):
    result = set()
    count = 0
    with zipfile.ZipFile(apk_file) as apk:
        for name in apk.namelist():
            if not re.fullmatch(r"classes(?:\d+)?\.dex", name):
                continue
            data = apk.read(name)
            if data[:4] != b"dex\n":
                raise ValueError(f"Unsupported DEX format: {name}")
            string_size, string_off = struct.unpack_from("<2I", data, 0x38)
            strings = [
                string_at(data, struct.unpack_from("<I", data, string_off + i*4)[0])
                for i in range(string_size)
            ]
            type_size, type_off = struct.unpack_from("<2I", data, 0x40)
            types = [strings[struct.unpack_from("<I", data, type_off + i*4)[0]]
                     for i in range(type_size)]
            class_size, class_off = struct.unpack_from("<2I", data, 0x60)
            for i in range(class_size):
                index = struct.unpack_from("<I", data, class_off + i*32)[0]
                result.add(types[index])
            count += 1
    return result, count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("whatsapp_apk")
    args = parser.parse_args()
    classes, dex_count = defined_classes(args.whatsapp_apk)
    expected = {
        "HomeActivity": "Lcom/whatsapp/home/ui/HomeActivity;",
        "SendReadReceiptJob":
            "Lcom/whatsapp/messaging/receipts/jobqueue/job/SendReadReceiptJob;",
        "ConversationsFragment": "Lcom/whatsapp/conversationslist/ConversationsFragment;",
        "WDSBottomBar": "Lcom/whatsapp/ui/wds/components/bottombar/WDSBottomBar;",
    }
    print(f"DEX files: {dex_count}, class definitions: {len(classes)}")
    missing = []
    for name, descriptor in expected.items():
        exists = descriptor in classes
        print(f"{name}: {'FOUND' if exists else 'MISSING'} ({descriptor})")
        if not exists:
            missing.append(name)
    if missing:
        raise SystemExit("Missing host class location(s): " + ", ".join(missing))


if __name__ == "__main__":
    main()
