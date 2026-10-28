#!/usr/bin/env python3
import sys
import os
import shutil
import struct
import plistlib
import subprocess

def patch_macho_uuid_data(data: bytearray, slice_offset=0):
    if len(data) < slice_offset + 32:
        return False
    magic = struct.unpack('<I', data[slice_offset:slice_offset+4])[0]
    if magic in (0xfeedfacf, 0xcffaedfe): # 64-bit Mach-O
        is_le = (magic == 0xfeedfacf)
        endian = '<' if is_le else '>'
        _, _, _, _, ncmds, sizeofcmds, _, _ = struct.unpack(endian + '8I', data[slice_offset:slice_offset+32])
        cmd_offset = slice_offset + 32
        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack(endian + '2I', data[cmd_offset:cmd_offset+8])
            if cmd == 0x1B: # LC_UUID
                data[cmd_offset + 8] = (data[cmd_offset + 8] + 1) & 0xFF
                return True
            cmd_offset += cmdsize
    elif magic in (0xfeedface, 0xcefaedfe): # 32-bit Mach-O
        is_le = (magic == 0xfeedface)
        endian = '<' if is_le else '>'
        _, _, _, _, ncmds, sizeofcmds, _ = struct.unpack(endian + '7I', data[slice_offset:slice_offset+28])
        cmd_offset = slice_offset + 28
        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack(endian + '2I', data[cmd_offset:cmd_offset+8])
            if cmd == 0x1B: # LC_UUID
                data[cmd_offset + 8] = (data[cmd_offset + 8] + 1) & 0xFF
                return True
            cmd_offset += cmdsize
    return False

def patch_macho_uuid(path):
    with open(path, 'rb') as f:
        data = bytearray(f.read())
    if len(data) < 4:
        return False
    magic = struct.unpack('>I', data[:4])[0]
    changed = False
    if magic == 0xcafebabe: # FAT 32-bit
        nfat = struct.unpack('>I', data[4:8])[0]
        for i in range(nfat):
            arch_offset = 8 + i * 20
            slice_offset = struct.unpack('>I', data[arch_offset+8:arch_offset+12])[0]
            if patch_macho_uuid_data(data, slice_offset):
                changed = True
    elif magic == 0xcafebabf: # FAT 64-bit
        nfat = struct.unpack('>I', data[4:8])[0]
        for i in range(nfat):
            arch_offset = 8 + i * 32
            slice_offset = struct.unpack('>Q', data[arch_offset+8:arch_offset+16])[0]
            if patch_macho_uuid_data(data, slice_offset):
                changed = True
    else:
        changed = patch_macho_uuid_data(data, 0)
    
    if changed:
        with open(path, 'wb') as f:
            f.write(data)
        print(f"[LC2] Patched Mach-O UUID for {path}")
    else:
        print(f"[LC2] Warning: LC_UUID not found or not modified in {path}")
    return changed

def make_livecontainer2(src_app, output_ipa):
    bundle_name = "LiveContainer2"
    display_name = "Books"
    bundle_id = f"com.kdt.{bundle_name}"
    url_scheme = bundle_name.lower()
    icon_name = "AppIconBooks"

    print(f"[LC2] Source App: {src_app}")
    print(f"[LC2] Target Output: {output_ipa}")
    print(f"[LC2] Display Name = {display_name}")
    print(f"[LC2] Bundle ID = {bundle_id}")
    print(f"[LC2] URL Scheme = {url_scheme}")

    tmp_work_dir = "tmp_lc2_build"
    if os.path.exists(tmp_work_dir):
        shutil.rmtree(tmp_work_dir)
    payload_dir = os.path.join(tmp_work_dir, "Payload")
    os.makedirs(payload_dir, exist_ok=True)

    dest_app = os.path.join(payload_dir, "App.app")
    print(f"[LC2] Copying app bundle to {dest_app}...")
    shutil.copytree(src_app, dest_app, symlinks=True)

    # 1. Update Info.plist
    info_path = os.path.join(dest_app, "Info.plist")
    with open(info_path, 'rb') as f:
        info_dict = plistlib.load(f)

    info_dict['CFBundleDisplayName'] = display_name
    info_dict['CFBundleName'] = bundle_name
    info_dict['CFBundleIdentifier'] = bundle_id
    
    url_types = info_dict.get('CFBundleURLTypes', [])
    if url_types and len(url_types) > 0:
        url_types[0]['CFBundleURLSchemes'] = [url_scheme]
        # Keep only the primary URL scheme for LiveContainer2
        info_dict['CFBundleURLTypes'] = [url_types[0]]
    else:
        info_dict['CFBundleURLTypes'] = [{
            'CFBundleURLName': f"{bundle_id}.urlscheme",
            'CFBundleURLSchemes': [url_scheme]
        }]

    if 'UTExportedTypeDeclarations' in info_dict:
        del info_dict['UTExportedTypeDeclarations']

    info_dict['CFBundleIconName'] = icon_name

    icons_dict = info_dict.get('CFBundleIcons')
    if isinstance(icons_dict, dict):
        primary = icons_dict.get('CFBundlePrimaryIcon')
        if isinstance(primary, dict):
            primary['CFBundleIconName'] = icon_name
            primary['CFBundleIconFiles'] = [f"{icon_name}60x60"]
    else:
        info_dict['CFBundleIcons'] = {
            'CFBundlePrimaryIcon': {
                'CFBundleIconName': icon_name,
                'CFBundleIconFiles': [f"{icon_name}60x60"]
            }
        }

    icons_ipad_dict = info_dict.get('CFBundleIcons~ipad')
    if isinstance(icons_ipad_dict, dict):
        primary = icons_ipad_dict.get('CFBundlePrimaryIcon')
        if isinstance(primary, dict):
            primary['CFBundleIconName'] = icon_name
            primary['CFBundleIconFiles'] = [f"{icon_name}60x60", f"{icon_name}76x76"]
    else:
        info_dict['CFBundleIcons~ipad'] = {
            'CFBundlePrimaryIcon': {
                'CFBundleIconName': icon_name,
                'CFBundleIconFiles': [f"{icon_name}60x60", f"{icon_name}76x76"]
            }
        }

    old_exec_name = info_dict.get('CFBundleExecutable', 'LiveContainer')
    info_dict['CFBundleExecutable'] = bundle_name

    # Remove SideStore intent / user activity declarations if present
    for key in ['INIntentsSupported', 'NSUserActivityTypes']:
        if key in info_dict:
            del info_dict[key]

    with open(info_path, 'wb') as f:
        plistlib.dump(info_dict, f)
    print("[LC2] Info.plist updated.")

    # 2. Rename executable
    old_exec_path = os.path.join(dest_app, old_exec_name)
    new_exec_path = os.path.join(dest_app, bundle_name)
    if os.path.exists(old_exec_path):
        os.rename(old_exec_path, new_exec_path)
        print(f"[LC2] Renamed executable: {old_exec_name} -> {bundle_name}")
    else:
        print(f"[LC2] Error: executable {old_exec_path} not found!")

    # 3. Patch Mach-O UUID
    if os.path.exists(new_exec_path):
        patch_macho_uuid(new_exec_path)

    # 4. Remove PlugIns directory
    plugins_path = os.path.join(dest_app, "PlugIns")
    if os.path.exists(plugins_path):
        shutil.rmtree(plugins_path, ignore_errors=True)
        print("[LC2] Removed PlugIns.")

    # 5. Remove SideStore files if present
    sidestore_files = [
        "Frameworks/SideStoreSupport.framework",
        "Frameworks/SideStore.framework",
        "Frameworks/SideStoreApp.framework",
        "Intents.intentdefinition",
        "ViewApp.intentdefinition",
        "Metadata.appintents"
    ]
    for rel_path in sidestore_files:
        full_p = os.path.join(dest_app, rel_path)
        if os.path.exists(full_p):
            if os.path.isdir(full_p):
                shutil.rmtree(full_p, ignore_errors=True)
            else:
                os.remove(full_p)

    # 6. Remove localized InfoPlist.strings so Tips is not displayed
    for item in os.listdir(dest_app):
        if item.endswith('.lproj'):
            strings_file = os.path.join(dest_app, item, "InfoPlist.strings")
            if os.path.exists(strings_file):
                os.remove(strings_file)
    print("[LC2] Cleaned localized InfoPlist.strings.")

    # 7. Ensure loose AppIconBooks files are in App.app
    res_dir = "Resources"
    for icon_file in [f"{icon_name}60x60@2x.png", f"{icon_name}76x76@2x~ipad.png"]:
        src_icon = os.path.join(res_dir, icon_file)
        dst_icon = os.path.join(dest_app, icon_file)
        if os.path.exists(src_icon) and not os.path.exists(dst_icon):
            shutil.copyfile(src_icon, dst_icon)
            print(f"[LC2] Copied {icon_file} to app bundle root.")

    # 8. Re-sign with ldid
    ent_xml_path = os.path.join(tmp_work_dir, "entitlements.xml")
    has_ent = False
    
    # Try extracting entitlements from original binary
    try:
        proc = subprocess.run(["ldid", "-e", old_exec_path if os.path.exists(old_exec_path) else src_app + f"/{old_exec_name}"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0 and proc.stdout and "<plist" in proc.stdout:
            ent_content = proc.stdout
            ent_content = ent_content.replace("com.kdt.livecontainer", bundle_id)
            ent_content = ent_content.replace("com.kdt.LiveContainer", bundle_id)
            ent_content = ent_content.replace(f".{old_exec_name}", f".{bundle_name}")
            with open(ent_xml_path, "w", encoding="utf-8") as f:
                f.write(ent_content)
            has_ent = True
            print("[LC2] Extracted and adjusted entitlements via ldid.")
    except Exception as e:
        print(f"[LC2] Note: could not extract entitlements with ldid ({e})")

    if not has_ent and os.path.exists("entitlements.xml"):
        with open("entitlements.xml", "r", encoding="utf-8") as f:
            ent_content = f.read()
        ent_content = ent_content.replace("$(PRODUCT_BUNDLE_IDENTIFIER)", bundle_id)
        ent_content = ent_content.replace("com.kdt.livecontainer", bundle_id)
        ent_content = ent_content.replace("$(DEVELOPMENT_TEAM)", "AAAAA11111")
        ent_content = ent_content.replace("$(APP_GROUP_SIDESTORE)", "group.com.SideStore.SideStore")
        ent_content = ent_content.replace("$(APP_GROUP_ALTSTORE)", "group.com.rileytestut.AltStore")
        with open(ent_xml_path, "w", encoding="utf-8") as f:
            f.write(ent_content)
        has_ent = True

    try:
        if has_ent:
            subprocess.run(["ldid", f"-S{ent_xml_path}", new_exec_path], check=True)
        else:
            subprocess.run(["ldid", "-S", new_exec_path], check=True)
        print("[LC2] Signed executable with ldid.")
    except Exception as e:
        print(f"[LC2] Warning: ldid signing skipped or failed: {e}")

    # 9. Package into IPA
    abs_output = os.path.abspath(output_ipa)
    if os.path.exists(abs_output):
        os.remove(abs_output)

    # Use system zip if available
    zip_success = False
    try:
        curr_cwd = os.getcwd()
        os.chdir(tmp_work_dir)
        proc = subprocess.run(["zip", "-r", abs_output, "Payload", "-x", "._*", "-x", ".DS_Store", "-x", "__MACOSX"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.chdir(curr_cwd)
        if proc.returncode == 0 and os.path.exists(abs_output):
            zip_success = True
            print(f"[LC2] Packaged {abs_output} using zip command.")
    except Exception as e:
        print(f"[LC2] zip command failed ({e}), falling back to zipfile module.")
        os.chdir(curr_cwd)

    if not zip_success:
        import zipfile
        with zipfile.ZipFile(abs_output, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(payload_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, tmp_work_dir)
                    zipf.write(full_p, rel_p)
        print(f"[LC2] Packaged {abs_output} using zipfile module.")

    shutil.rmtree(tmp_work_dir, ignore_errors=True)
    print(f"[LC2] Successfully generated {abs_output}!")

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else "Payload/LiveContainer.app"
    out = sys.argv[2] if len(sys.argv) > 2 else "LiveContainer2.ipa"
    make_livecontainer2(src, out)
