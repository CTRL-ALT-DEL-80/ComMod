import os
import winreg

from ctypes import windll
import logging

import data
import utils
from get_system_fonts import get_fonts

def get_monitor_resolution():
    res_x = windll.user32.GetSystemMetrics(0)
    res_y = windll.user32.GetSystemMetrics(1)
    screen_size = int(res_x), int(res_y)
    logging.debug(f"reported res x: {res_x}")
    logging.debug(f"reported res y: {res_y}")
    logging.debug(f"os scale factor: {data.OS_SCALE_FACTOR}")
    logging.debug(f"screen size {screen_size[0]}:{screen_size[1]}")
    return screen_size


def scale_fonts(root_dir: str, scale_factor):
    config = utils.get_config(root_dir)
    ui_schema_path = os.path.join(root_dir, config.attrib.get("ui_pathToSchema"))
    ui_schema = utils.xml_to_objfy(ui_schema_path)

    system_fonts = [font.lower() for font in os.listdir(r'C:\Windows\fonts')]

    tahoma_available = False
    arial_available = False
    force_arial = True

    if "tahoma.ttf" in system_fonts:
        tahoma_alias = "Tahoma"
        tahoma_available = True

    arial_available = "arial.ttf" in system_fonts

    if (not tahoma_available and not force_arial) or not arial_available:
        system_fonts = get_fonts()
        if "Tahoma" in system_fonts:
            tahoma_alias = "Tahoma"
            tahoma_available = True
        elif "SM_Tahoma" in system_fonts:
            tahoma_alias = "SM_Tahoma"
            tahoma_available = True
        else:
            tahoma_available = False
        
        arial_available = "Arial" in system_fonts
    
    if ((not tahoma_available) and arial_available) or force_arial:
        tahoma_alias = "Arial"
        tahoma_available = True

    if arial_available:
        if ui_schema["schema"].attrib.get("titleFontSize") is not None and tahoma_available:
            ui_schema["schema"].attrib["titleFontFace"] = tahoma_alias
            ui_schema["schema"].attrib["titleFontSize"] = f"{round(12 / data.OS_SCALE_FACTOR * data.ENLARGE_UI_COEF, 1)}"
            ui_schema["schema"].attrib["titleFontType"] = "0"
        if ui_schema["schema"].attrib.get("wndFontSize") is not None and tahoma_available:
            ui_schema["schema"].attrib["wndFontFace"] = tahoma_alias
            ui_schema["schema"].attrib["wndFontSize"] = f"{round(10 / data.OS_SCALE_FACTOR * data.ENLARGE_UI_COEF, 1)}"
            ui_schema["schema"].attrib["wndFontType"] = "0"
        if ui_schema["schema"].attrib.get("tooltipFontSize") is not None and tahoma_available:
            ui_schema["schema"].attrib["tooltipFontFace"] = tahoma_alias
            ui_schema["schema"].attrib["tooltipFontSize"] = f"{round(12 / data.OS_SCALE_FACTOR * data.ENLARGE_UI_COEF, 1)}"
            ui_schema["schema"].attrib["tooltipFontType"] = "0"
        if ui_schema["schema"].attrib.get("miscFontSize") is not None and arial_available:
            ui_schema["schema"].attrib["miscFontFace"] = "Arial"
            ui_schema["schema"].attrib["miscFontSize"] = f"{round(10 / data.OS_SCALE_FACTOR * data.ENLARGE_UI_COEF, 1)}"
            ui_schema["schema"].attrib["miscFontType"] = "0"
        utils.save_to_file(ui_schema, ui_schema_path)
        logging.debug(utils.loc_string("fonts_corrected"))
    else:
        print(utils.loc_string("cant_correct_fonts"))

def make_dpi_aware(path_to_exe):
    compat_settings_reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
    hklm = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
    compat_settings_reg_value = winreg.OpenKey(hklm, compat_settings_reg_path, 0, winreg.KEY_WRITE)
    winreg.SetValueEx(compat_settings_reg_value, os.path.normpath(path_to_exe), 0, winreg.REG_SZ, "~ HIGHDPIAWARE")
    winreg.SetValueEx(compat_settings_reg_value, os.path.normpath(path_to_exe), 0, winreg.REG_SZ, "~ HIGHDPIAWARE")

    hkcu = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)



def toggle_16_9_UI_xmls(root_dir: str, screen_width, screen_height, enable=True):
    config = utils.get_config(root_dir)
    if config.attrib.get("pathToUiWindows") is not None:
        if enable:
            new_value = r"data\if\dialogs_16_9\UiWindows.xml"
        else:
            new_value = r"data\if\dialogs\UiWindows.xml"
        config.attrib["pathToUiWindows"] = new_value

    if config.attrib.get("pathToCredits") is not None:
        if enable:
            new_value = r"data\if\dialogs_16_9\credits.xml"
        else:
            new_value = r"data\if\dialogs\credits.xml"
        config.attrib["pathToCredits"] = new_value

    if config.attrib.get("ui_pathToFrames") is not None:
        if enable:
            new_value = r"data\if\frames\frames_hd.xml"
        else:
            new_value = r"data\if\frames\frames.xml"
        config.attrib["ui_pathToFrames"] = new_value

    if config.attrib.get("pathToSplashes") is not None:
        if enable:
            new_value = r"data\if\ico_hd\splashes.xml"
        else:
            new_value = r"data\if\ico\splashes.xml"
        config.attrib["pathToSplashes"] = new_value

    if config.attrib.get("pathToUiIcons") is not None:
        if enable:
            new_value = r"data\if\ico_hd\UiIcons.xml"
        else:
            new_value = r"data\if\ico\UiIcons.xml"
        config.attrib["pathToUiIcons"] = new_value

    if config.attrib.get("pathToLevelInfo") is not None:
        if enable:
            new_value = r"data\if\diz\LevelInfo_hd.xml"
        else:
            new_value = r"data\if\diz\LevelInfo.xml"
        config.attrib["pathToLevelInfo"] = new_value

    width = config.attrib.get("r_width")
    height = config.attrib.get("r_height")
    if width is not None and height is not None:
        if enable:
            good_width = screen_width in list(data.possible_resolutions.keys())
            good_heigth = data.possible_resolutions.get(screen_width) == screen_height
            if width == "1024" and height == "768":
                if good_width and good_heigth:
                    new_width = str(screen_width)
                    new_height = str(screen_height)
            else:
                if not (good_width and good_heigth):
                    new_width = "1280"
                    new_height = "720"
                else:
                    new_width = str(screen_width)
                    new_height = str(screen_height)
        else:
            if width == "1280" and height == "720":
                new_width = "1024"
                new_height = "768"
        if not (width == "1920" or width == "2560" or width == "3840") and new_width and new_height:
            config.attrib["r_width"] = new_width
            config.attrib["r_height"] = new_height

    utils.save_to_file(config, os.path.join(root_dir, "data", "config.cfg"))

def toggle_16_9_glob_prop(root_dir: str, enable=True):
    glob_props_full_path = os.path.join(root_dir, utils.get_glob_props_path(root_dir))
    glob_props = utils.xml_to_objfy(glob_props_full_path)
    ground_repository = utils.child_from_xml_node(glob_props, "GroundRepository")
    smart_cursor = utils.child_from_xml_node(glob_props, "SmartCursor")
    if ground_repository is not None:
        if enable:
            ground_repository.attrib["Size"] = "18 300"
        else:
            ground_repository.attrib["Size"] = "13 10000"
    if smart_cursor is not None:
        if enable:
            smart_cursor.attrib["InfoAreaRadius"] = "70"
            smart_cursor.attrib["UnlockRegion"] = "422 422"
            smart_cursor.attrib["InfoObjUpdateTimeout"] = "0.2"
        else:
            smart_cursor.attrib["InfoAreaRadius"] = "50"
            smart_cursor.attrib["UnlockRegion"] = "300 300"
            smart_cursor.attrib["InfoObjUpdateTimeout"] = "0.5"
    utils.save_to_file(glob_props, glob_props_full_path)

