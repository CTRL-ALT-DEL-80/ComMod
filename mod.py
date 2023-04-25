from __future__ import annotations
from functools import total_ordering

import logging
import operator
import os
from pathlib import Path
import typing

from enum import Enum

from color import bcolors, fconsole, remove_colors
from localisation import tr, DEM_DISCORD, COMPATCH_GITHUB, WIKI_COMPATCH
from file_ops import copy_from_to, read_yaml, process_markdown, get_internal_file_path

logger = logging.getLogger('dem')


class Mod:
    '''Mod for HTA/EM, contains mod data, installation instructions
       and related functions'''
    def __init__(self, yaml_config: dict, distribution_dir: str) -> None:
        try:
            self.name = str(yaml_config.get("name"))[:64].replace("/", "").replace("\\", "").replace(".", "").strip()
            self.display_name = str(yaml_config.get("display_name"))[:64].strip()
            self.description = str(yaml_config.get("description"))[:2048].strip()
            self.authors = str(yaml_config.get("authors"))[:256].strip()
            self.version = str(yaml_config.get("version"))[:64].strip()
            self.build = str(yaml_config.get("build"))[:7].strip()
            url = yaml_config.get("link")
            trailer_url = yaml_config.get("trailer_link")
            self.url = url[:128].strip() if url is not None else ""
            self.trailer_url = trailer_url[:128].strip() if trailer_url is not None else ""
            self.prerequisites = yaml_config.get("prerequisites")
            self.incompatible = yaml_config.get("incompatible")
            self.individual_require_status = []
            self.individual_incomp_status = []
            self.requirements_style = "mixed"
            self.incompatibles_style = "mixed"
            self.release_date = yaml_config.get("release_date")
            self.tags = yaml_config.get("tags")
            self.logo = yaml_config.get("logo")
            self.install_banner = yaml_config.get("install_banner")
            self.language = yaml_config.get("language")
            self.screenshots = yaml_config.get("screenshots")
            self.change_log = yaml_config.get("change_log")
            self.other_info = yaml_config.get("other_info")

            translations = yaml_config.get("translations")
            self.translations = {}
            self.translations_loaded = {}
            if translations is not None:
                for translation in translations:
                    self.translations[translation] = Mod.is_known_lang(translation)

            if self.release_date is None:
                self.release_date = ""

            if self.tags is None:
                self.tags = [Mod.Tags.UNCATEGORIZED.name]
            else:
                # removing unknown values
                self.tags = list(set([tag.upper() for tag in self.tags]) & set(Mod.Tags.list_names()))

            if self.screenshots is None:
                self.screenshots = []
            elif isinstance(self.screenshots, list):
                for screenshot in self.screenshots:
                    if not isinstance(screenshot.get("img"), str):
                        next

                    if isinstance(screenshot.get("text"), str):
                        screenshot["text"] = screenshot["text"].strip()
                    else:
                        screenshot["text"] = ""
                    if isinstance(screenshot.get("compare"), str):
                        pass
                    else:
                        screenshot["compare"] = ""

            if self.change_log is None:
                self.change_log = ""

            if self.other_info is None:
                self.other_info = ""

            # to simplify hadling of incomps and reqs
            # we always work with them as if they are list of choices
            if self.prerequisites is None:
                self.prerequisites = []
            elif isinstance(self.prerequisites, list):
                for prereq in self.prerequisites:
                    if isinstance(prereq.get("name"), str):
                        prereq["name"] = [prereq["name"]]
                    if isinstance(prereq.get("versions"), str):
                        prereq["versions"] = [prereq["versions"]]

            if self.incompatible is None:
                self.incompatible = []
            elif isinstance(self.incompatible, list):
                for incomp in self.incompatible:
                    if isinstance(incomp.get("name"), str):
                        incomp["name"] = [incomp["name"]]
                    if isinstance(incomp.get("versions"), str):
                        incomp["versions"] = [incomp["versions"]]

            patcher_version_requirement = yaml_config.get("patcher_version_requirement")
            if patcher_version_requirement is None:
                self.patcher_version_requirement = [">=1.10"]
            elif not isinstance(patcher_version_requirement, list):
                self.patcher_version_requirement = [str(patcher_version_requirement)]
            else:
                self.patcher_version_requirement = [str(ver) for ver in patcher_version_requirement]

            self.patcher_options = yaml_config.get("patcher_options")

            self.distibution_dir = distribution_dir
            self.options_dict = {}
            self.no_base_content = False

            no_base_content = yaml_config.get("no_base_content")
            if no_base_content is not None:
                if isinstance(no_base_content, bool):
                    self.no_base_content = no_base_content
                else:
                    no_base_content = str(no_base_content)

                    if no_base_content.lower() == "true":
                        self.no_base_content = True
                    elif no_base_content.lower() == "false":
                        pass
                    else:
                        raise ValueError(f"Broken manifest for content '{self.name}'!")

            self.optional_content = None

            optional_content = yaml_config.get("optional_content")
            if optional_content and optional_content is not None:
                self.optional_content = []
                if isinstance(optional_content, list):
                    for option in optional_content:
                        option_loaded = Mod.OptionalContent(option, self)
                        self.optional_content.append(option_loaded)
                        self.options_dict[option_loaded.name] = option_loaded
                else:
                    raise ValueError(f"Broken manifest for optional part of content '{self.name}'!")

        except Exception as ex:
            er_message = f"Broken manifest for content '{self.name}'!"
            logger.error(ex)
            logger.error(er_message)
            raise ValueError(er_message)

    @staticmethod
    def is_known_lang(lang: str):
        return lang in ["eng", "ru", "ua", "de", "pl", "tr"]

    def load_translations(self, load_gui_info: bool = False):
        self.translations_loaded[self.language] = self
        if load_gui_info:
            self.load_gui_info()
        if self.translations:
            for lang, _ in self.translations.items():
                lang_manifest_path = Path(self.distibution_dir, f"manifest_{lang}.yaml")
                if not lang_manifest_path.exists():
                    raise ValueError(f"Lang '{lang}' specified but manifest for it is missing! "
                                     f"(Mod: {self.name})")
                yaml_config = read_yaml(lang_manifest_path)
                config_validated = Mod.validate_install_config(yaml_config, lang_manifest_path)
                if config_validated:
                    mod_tr = Mod(yaml_config, self.distibution_dir)
                    if mod_tr.name != self.name:
                        raise ValueError("Service name missmatch in translation: "
                                         f"'{mod_tr.name}' name specified for translation, "
                                         f"but main mod name is '{self.name}'! "
                                         f"(Mod: {self.name}) (Translation: {mod_tr.language})")
                    if mod_tr.version != self.version:
                        raise ValueError("Version missmatch: "
                                         f"'{mod_tr.version}' specified for translation, "
                                         f"but main mod version is '{self.version}'! "
                                         f"(Mod: {self.name}) (Translation: {mod_tr.language})")
                    if sorted(mod_tr.tags) != sorted(self.tags):
                        raise ValueError("Tags missmatch: "
                                         f"{mod_tr.tags} specified for translation, "
                                         f"but main mod tags are {self.tags}! "
                                         f"(Mod: {self.name}) (Translation: {mod_tr.language})")
                    if mod_tr.language != lang:
                        raise ValueError("Language missmatch for translation manifest name and info: "
                                         f"{mod_tr.language} in manifest, {lang} in manifest name! "
                                         f"(Mod: {self.name})")
                    if mod_tr.language == self.language:
                        raise ValueError("Language duplication for translation manifest: "
                                         f"{lang} in manifest, but {lang} is main lang already! "
                                         f"(Mod: {self.name})")

                    self.translations_loaded[lang] = mod_tr
                    if load_gui_info:
                        mod_tr.load_gui_info()

        for lang, mod in self.translations_loaded.items():
            mod.known_language = self.is_known_lang(lang)
            if mod.known_language:
                mod.lang_label = tr(lang)
            else:
                mod.lang_label = lang

    def load_gui_info(self):
        supported_img_extensions = [".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]
        self.change_log_content = ""
        if self.change_log:
            changelog_path = Path(self.distibution_dir, self.change_log)
            if changelog_path.exists() and changelog_path.suffix.lower() == ".md":
                with open(changelog_path, "r", encoding="utf-8") as fh:
                    md = fh.read()
                    md = process_markdown(md)
                    self.change_log_content = md

        self.other_info_content = ""
        if self.other_info:
            other_info_path = Path(self.distibution_dir, self.other_info)
            if other_info_path.exists() and other_info_path.suffix.lower() == ".md":
                with open(other_info_path, "r", encoding="utf-8") as fh:
                    md = fh.read()
                    md = process_markdown(md)
                    self.other_info_content = md

        self.logo_path = get_internal_file_path("assets/no_logo.png")
        if isinstance(self.logo, str):
            logo_path = Path(self.distibution_dir, self.logo)
            if logo_path.exists() and logo_path.suffix.lower() in supported_img_extensions:
                self.logo_path = str(logo_path)

        self.banner_path = None
        if isinstance(self.install_banner, str):
            banner_path = Path(self.distibution_dir, self.install_banner)
            if banner_path.exists() and banner_path.suffix.lower() in supported_img_extensions:
                self.banner_path = str(banner_path)

        for screen in self.screenshots:
            screen_path = Path(self.distibution_dir, screen["img"])
            if screen_path.exists() and screen_path.suffix.lower() in supported_img_extensions:
                screen["path"] = str(screen_path)
            else:
                screen["path"] = ""
                logger.warning(f"Missing path for screenshot ({screen['img']}) "
                               f"in mod {self.name}-{self.language}")

            compare_path = Path(self.distibution_dir, screen["compare"])
            if compare_path.exists() and compare_path.suffix.lower() in supported_img_extensions:
                screen["compare_path"] = str(compare_path)
                if screen["text"]:
                    screen["text"] += "\n"
                screen["text"] = screen["text"] + f'({tr("click_screen_to_compare")})'
            else:
                screen["compare_path"] = ""

        # we ignore screens which do not exist
        self.screenshots = [screen for screen in self.screenshots if screen["path"]]

        if ", " in self.authors:
            self.developer_title = "authors"
        else:
            self.developer_title = "author"

    def load_commod_compatibility(self, commod_version):
        for translation in self.translations_loaded.values():
            translation.commod_compatible, translation.commod_compatible_err = \
                translation.compatible_with_mod_manager(commod_version)

    def load_session_compatibility(self, installed_content, installed_descriptions):
        for translation in self.translations_loaded.values():
            # self.commod_compatible = compat_info["compatible_with_commod"]
            # self.commod_compatible_err = remove_colors(compat_info["compatible_with_commod_err"].strip())

            # compatible = compat_info.get("compatible")
            # if compatible is not None:
            #     self.compatible = compatible
            #     self.compatible_err = "\n".join(compat_info["compatible_err"]).strip()
            # else:
            #     self.compatible = True
            #     self.compatible_err = ""
            translation.compatible, translation.compatible_err = \
                translation.check_requirements(
                    installed_content,
                    installed_descriptions)

            translation.compatible_err = "\n".join(translation.compatible_err).strip()

            # prevalidated = compat_info.get("prevalidated")
            # if prevalidated is not None:
            #     self.prevalidated = prevalidated
            #     self.prevalidated_err = "\n".join(compat_info["prevalidated_err"]).strip()
            # else:
            #     self.prevalidated = True
            #     self.prevalidated_err = ""

            translation.prevalidated, translation.prevalidated_err = \
                translation.check_incompatibles(
                    installed_content,
                    installed_descriptions)

            translation.prevalidated_err = "\n".join(translation.prevalidated_err).strip()

            (translation.is_reinstall, translation.can_be_reinstalled,
             translation.reinstall_warning, translation.existing_version) = \
                translation.check_reinstallability(
                    installed_content,
                    installed_descriptions)

            translation.can_install = (translation.commod_compatible
                                       and translation.compatible
                                       and translation.prevalidated
                                       and translation.can_be_reinstalled)

    def install(self, game_data_path: str,
                install_settings: dict,
                existing_content: dict,
                existing_content_descriptions: dict,
                console: bool = False) -> tuple[bool, list]:
        '''Returns bool success status of install and errors list in case mod requirements are not met'''
        try:
            logger.info(f"Existing content: {existing_content}")
            mod_files = []
            requirements_met, error_msgs = self.check_requirements(existing_content,
                                                                   existing_content_descriptions)
            if requirements_met:
                for install_setting in install_settings:
                    if install_setting == "base":
                        install_base = install_settings.get('base')
                        if install_base is None:
                            raise KeyError(f"Installation config for base of mod '{self.name}' is broken")
                        if self.optional_content is not None:
                            for option in self.optional_content:
                                option_config = install_settings.get(option.name)
                                if option_config is None:
                                    raise KeyError(f"Installation config for option '{option.name}'"
                                                   f" of mod '{self.name}' is broken")
                        base_path = os.path.join(self.distibution_dir, "data")
                        if console:
                            if self.name == "community_remaster":
                                print("\n")  # separator
                            print(fconsole(tr("copying_base_files_please_wait"), bcolors.RED)
                                  + "\n")
                        mod_files.append(base_path)
                    else:
                        wip_setting = self.options_dict[install_setting]
                        base_work_path = os.path.join(self.distibution_dir, wip_setting.name, "data")
                        installation_prompt_result = install_settings[install_setting]
                        if installation_prompt_result == "yes":
                            mod_files.append(base_work_path)
                        elif installation_prompt_result == "skip":
                            pass
                        else:
                            custom_install_method = install_settings[install_setting]
                            custom_install_work_path = os.path.join(self.distibution_dir,
                                                                    wip_setting.name,
                                                                    custom_install_method)

                            mod_files.append(base_work_path)
                            mod_files.append(custom_install_work_path)
                        if console and installation_prompt_result != "skip":
                            print(fconsole(tr("copying_options_please_wait"), bcolors.RED) + "\n")
                copy_from_to(mod_files, game_data_path, console)
                return True, []
            else:
                return False, error_msgs
        except Exception as ex:
            logger.error(ex)
            return False, []

    def check_requirement(self, prereq: dict, existing_content: dict,
                          existing_content_descriptions: dict,
                          is_compatch_env: bool) -> tuple[bool, str]:
        error_msg = []
        required_mod_name = None

        name_validated = True
        version_validated = True
        optional_content_validated = True

        for possible_prereq_mod in prereq['name']:
            existing_mod = existing_content.get(possible_prereq_mod)
            if existing_mod is not None:
                required_mod_name = possible_prereq_mod

        if required_mod_name is None:
            name_validated = False

        # if trying to install compatch-only mod on comrem
        if (required_mod_name == "community_patch"
           and existing_content.get("community_remaster") is not None
           and self.name != "community_remaster"
           and "community_remaster" not in prereq["name"]):
            name_validated = False
            error_msg.append(f"{tr('compatch_mod_incompatible_with_comrem')}")

        or_word = f" {tr('or')} "
        and_word = f" {tr('and')} "
        only_technical_name_available = False

        name_label = []
        # TODO: need a better way to fetch display names for prereqs and incompats
        for service_name in prereq["name"]:
            existing_mod = existing_content.get(service_name)
            if existing_mod is not None:
                name_label.append(existing_mod["display_name"])
            else:
                name_label.append(service_name)
                only_technical_name_available = True

        name_label = or_word.join(name_label)
        version_label = ""
        optional_content_label = ""

        prereq_versions = prereq.get("versions")
        if prereq_versions and prereq_versions is not None:
            version_label = (f', {tr("of_version")}: '
                             f'{and_word.join(prereq.get("versions"))}')
            if name_validated:
                compare_ops = set([])
                for version in prereq_versions:
                    if ">=" == version[:2]:
                        compare_operation = operator.ge
                    elif "<=" == version[:2]:
                        compare_operation = operator.le
                    elif ">" == version[:1]:
                        compare_operation = operator.gt
                    elif "<" == version[:1]:
                        compare_operation = operator.lt
                    else:  # default "version" treated the same as "==version":
                        compare_operation = operator.eq

                    for sign in (">", "<", "="):
                        version = version.replace(sign, '')

                    installed_version = existing_content[required_mod_name]["version"]
                    parsed_existing_ver = Mod.Version(installed_version)
                    parsed_required_ver = Mod.Version(version)

                    version_validated = compare_operation(parsed_existing_ver, parsed_required_ver)
                    compare_ops.add(compare_operation)
                    if compare_operation is operator.eq:
                        if parsed_required_ver.identifier:
                            if parsed_existing_ver.identifier != parsed_required_ver.identifier:
                                version_validated = False

                compare_ops = list(compare_ops)
                len_ops = len(compare_ops)
                if len_ops == 1 and operator.eq in compare_ops:
                    self.requirements_style = "strict"
                elif len_ops == 2 and operator.eq not in compare_ops:
                    if (compare_ops[0] in (operator.ge, operator.gt)
                       and compare_ops[1] in (operator.le, operator.lt)):
                        self.requirements_style = "range"
                    elif (compare_ops[0] in (operator.lt, operator.lt)
                          and compare_ops[1] in (operator.ge, operator.gt)):
                        self.requirements_style = "range"
                    else:
                        self.requirements_style = "mixed"
                else:
                    self.requirements_style = "mixed"

        optional_content = prereq.get("optional_content")
        if optional_content and optional_content is not None:
            optional_content_label = (f', {tr("including_options").lower()}: '
                                      f'{", ".join(prereq["optional_content"])}')
            if name_validated and version_validated:
                for option in optional_content:
                    if existing_content[required_mod_name].get(option) in [None, "skip"]:
                        optional_content_validated = False
                        requirement_err = f"{tr('content_requirement_not_met')}:"
                        requirement_name = (f"  * '{option}' {tr('for_mod')} "
                                            f"{name_label}")

                        if requirement_err not in error_msg:
                            error_msg.append(requirement_err)

                        error_msg.append(requirement_name)
                    else:
                        logger.info(f"content validated: {option} - for mod: {name_label}")

        validated = name_validated and version_validated and optional_content_validated

        if not validated:
            if not name_validated:
                warning = f'\n{tr("required_mod_not_found")}:'
            else:
                warning = f'\n{tr("required_base")}:'

            if warning not in error_msg:
                error_msg.append(warning)

            if only_technical_name_available:
                name_label_tr = tr("technical_name")
            else:
                name_label_tr = tr("mod_name")
            error_msg.append(f'{name_label_tr.capitalize()}: '
                             f'{name_label}{version_label}{optional_content_label}')
            installed_description = existing_content_descriptions.get(required_mod_name)
            if installed_description is not None:
                installed_description = installed_description.strip("\n\n")
                error_msg_entry = (f'\n{tr("version_available").capitalize()}:\n'
                                   f'{remove_colors(installed_description)}')
                if error_msg_entry not in error_msg:
                    error_msg.append(error_msg_entry)

            else:
                # in case when we working with compatched game but mod requires comrem
                # it would be nice to tip a user that this is incompatibility in itself
                if is_compatch_env and "community_remaster" in prereq["name"]:
                    installed_description = existing_content_descriptions.get("community_patch")
                    error_msg_entry = (f'\n{tr("version_available").capitalize()}:\n'
                                       f'{remove_colors(installed_description)}')
                    if error_msg_entry not in error_msg:
                        error_msg.append(error_msg_entry)
        prereq["name_label"] = name_label
        return validated, error_msg

    def check_requirements(self, existing_content: dict, existing_content_descriptions: dict,
                           patcher_version: str | float = '') -> tuple[bool, list]:
        error_msg = []

        requirements_met = True
        is_compatch_env = ("community_remaster" not in existing_content.keys() and
                           "community_patch" in existing_content.keys())

        if patcher_version:
            if not self.compatible_with_mod_manager(patcher_version):
                requirements_met &= False
                error_msg.append(f"{tr('usupported_patcher_version')}: "
                                 f"{self.display_name} - {self.patcher_version_requirement}"
                                 f" > {patcher_version}")

        self.individual_require_status.clear()
        for prereq in self.prerequisites:
            if self.name == "community_remaster" and prereq["name"][0] == "community_patch":
                continue

            validated, mod_error = self.check_requirement(prereq,
                                                          existing_content, existing_content_descriptions,
                                                          is_compatch_env)
            # TODO: might need to clear individual_require_status each time we check requirements
            self.individual_require_status.append((prereq, validated, mod_error))
            if mod_error:
                error_msg.extend(mod_error)
            requirements_met &= validated

        if error_msg:
            error_msg.append(f'\n{tr("check_for_a_new_version")}')

        return requirements_met, error_msg

    def check_reinstallability(self, existing_content: dict,
                               existing_content_descriptions: dict) -> tuple[bool, bool, str]:
        '''Returns is_reinstallation: bool, can_be_installed: bool, warning_text: str'''
        previous_install = existing_content.get(self.name)
        if self.name == "community_remaster":
            compatch_preivous = existing_content.get("community_patch")
            if previous_install is None:
                previous_install = compatch_preivous

        if previous_install is None:
            # no reinstall, can be installed
            return False, True, "", None

        self_and_prereqs = [self.name]
        for prereq in self.prerequisites:
            self_and_prereqs.extend(prereq["name"])

        existing_other_mods = set(existing_content.keys()) - set(self_and_prereqs)
        if existing_other_mods:
            # is reinstall, can't be installed as other mods not from prerequisites were installed
            existing_mods_display_names = []
            for name in existing_other_mods:
                mod_name = existing_content[name].get("display_name")
                if mod_name is None:
                    mod_name = name
                existing_mods_display_names.append(mod_name)
            warning = f'{tr("cant_reinstall_over_other_mods")}: ' + ", ".join(existing_mods_display_names)
            return True, False, warning, previous_install

        existing_version = Mod.Version(previous_install["version"])
        this_version = Mod.Version(self.version)
        if existing_version == this_version:
            if self.build == previous_install["build"]:
                if self.optional_content:
                    # is reinstall, complex mod, safe reinstall, forced options
                    return True, True, tr("complex_safe_reinstall"), previous_install
                else:
                    # is reinstall, simple mod, safe reinstall
                    return True, True, tr("safe_reinstall"), previous_install
            elif self.build > previous_install["build"]:
                if self.optional_content:
                    # is reinstall, complex mod, unsafe reinstall, forced options
                    return True, True, tr("complex_unsafe_reinstall"), previous_install
                else:
                    # is reinstall, simple mod, unsafe reinstall
                    return True, True, tr("unsafe_reinstall"), previous_install
            else:
                return True, False, tr("cant_reinstall_over_newer_build"), previous_install
        else:
            return True, False, tr("cant_reinstall_over_other_version"), previous_install

    def check_incompatible(self, incomp: dict, existing_content: dict,
                           existing_content_descriptions: dict) -> tuple[bool, list]:
        error_msg = []
        name_incompat = False
        version_incomp = False
        optional_content_incomp = False

        incomp_mod_name = None
        for possible_incomp_mod in incomp['name']:
            existing_mod = existing_content.get(possible_incomp_mod)
            if existing_mod is not None:
                incomp_mod_name = possible_incomp_mod

        or_word = f" {tr('or')} "
        # and_word = f" {tr('and')} "
        only_technical_name_available = False

        name_label = []
        # TODO: need a better way to fetch display names for prereqs and incompats
        for service_name in incomp["name"]:
            existing_mod = existing_content.get(service_name)
            if existing_mod is not None:
                name_label.append(existing_mod["display_name"])
            else:
                name_label.append(service_name)
                only_technical_name_available = True

        name_label = or_word.join(name_label)
        version_label = ""
        optional_content_label = ""

        if incomp_mod_name is not None:
            # if incompatible mod is found we need to check if a tighter conformity check exists
            name_incompat = True

            incomp_versions = incomp.get("versions")
            if incomp_versions and incomp_versions is not None:
                installed_version = existing_content[incomp_mod_name]["version"]

                version_label = (f', {tr("of_version")}: '
                                 f'{or_word.join(incomp.get("versions"))}')
                compare_ops = set([])
                for version in incomp_versions:
                    if ">=" == version[:2]:
                        compare_operation = operator.ge
                    elif "<=" == version[:2]:
                        compare_operation = operator.le
                    elif ">" == version[:1]:
                        compare_operation = operator.gt
                    elif "<" == version[:1]:
                        compare_operation = operator.lt
                    else:  # default "version" treated the same as "==version":
                        compare_operation = operator.eq

                    for sign in (">", "<", "="):
                        version = version.replace(sign, '')

                    parsed_existing_ver = Mod.Version(installed_version)
                    parsed_incompat_ver = Mod.Version(version)

                    version_incomp = compare_operation(parsed_existing_ver, parsed_incompat_ver)

                    compare_ops.add(compare_operation)
                    # while we ignore postfix for less/greater ops, we want to have an ability
                    # to make a specifix version with postfix incompatible
                    if compare_operation is operator.eq:
                        if parsed_incompat_ver.identifier:
                            if parsed_existing_ver.identifier != parsed_incompat_ver.identifier:
                                version_incomp = True

                compare_ops = list(compare_ops)
                len_ops = len(compare_ops)
                if len_ops == 1 and operator.eq in compare_ops:
                    self.incompatibles_style = "strict"
                elif len_ops == 2 and operator.eq not in compare_ops:
                    if (compare_ops[0] in (operator.ge, operator.gt)
                       and compare_ops[1] in (operator.le, operator.lt)):
                        self.incompatibles_style = "range"
                    elif (compare_ops[0] in (operator.lt, operator.lt)
                          and compare_ops[1] in (operator.ge, operator.gt)):
                        self.incompatibles_style = "range"
                    else:
                        self.incompatibles_style = "mixed"
                else:
                    self.incompatibles_style = "mixed"

            else:
                version_incomp = True

            optional_content = incomp.get("optional_content")

            if optional_content and optional_content is not None:

                optional_content_label = (f', {tr("including_options").lower()}: '
                                          f'{or_word.join(incomp.get("optional_content"))}')

                for option in optional_content:
                    if existing_content[incomp_mod_name].get(option) not in [None, "skip"]:
                        optional_content_incomp = True
            else:
                optional_content_incomp = True

            incompatible_with_game_copy = name_incompat and version_incomp and optional_content_incomp

            if only_technical_name_available:
                name_label_tr = tr("technical_name")
            else:
                name_label_tr = tr("mod_name")

            if incompatible_with_game_copy:
                error_msg.append(f'\n{tr("found_incompatible")}:\n'
                                 f'{name_label_tr.capitalize()}: '
                                 f'{name_label}{version_label}{optional_content_label}')
                installed_description = existing_content_descriptions.get(incomp_mod_name)
                if installed_description is not None:
                    installed_description = installed_description.strip("\n\n")
                    error_msg.append(f'\n{tr("version_available").capitalize()}:\n'
                                     f'{remove_colors(installed_description)}')
                else:
                    # TODO: check if this path even possible
                    raise NotImplementedError
            incomp["name_label"] = name_label
            return incompatible_with_game_copy, error_msg

        incomp["name_label"] = name_label
        return False, ""

    def check_incompatibles(self, existing_content: dict,
                            existing_content_descriptions: dict) -> tuple[bool, list]:
        error_msg = []
        compatible = True

        self.individual_incomp_status.clear()

        for incomp in self.incompatible:
            incompatible_with_game_copy, mod_error = self.check_incompatible(
                incomp, existing_content, existing_content_descriptions)
            self.individual_incomp_status.append((incomp, not incompatible_with_game_copy,
                                                 mod_error))
            if mod_error:
                error_msg.extend(mod_error)
            compatible &= (not incompatible_with_game_copy)

        if error_msg:
            error_msg.append(f'\n{tr("check_for_a_new_version")}')
            # if self.url is not None:
            #     error_msg.append(f"\n{loc_string('mod_url')} {self.url}")
        return compatible, error_msg

    def validate_install_config(install_config: typing.Any, mod_config_path: str,
                                skip_data_validation: bool = False) -> bool:
        mod_path = Path(mod_config_path).parent.parent
        is_dict = isinstance(install_config, dict)
        if is_dict:
            # schema type 1: list of possible types, required(bool)
            # schema type 2: list of possible types, required(bool), value[min, max]
            schema_fieds_top = {
                "name": [[str], True],
                "display_name": [[str], True],
                "version": [[str, int, float], True],
                "build": [[str], True],
                "description": [[str], True],
                "authors": [[str], True],
                "prerequisites": [[list], True],
                "incompatible": [[list], False],
                "patcher_version_requirement": [[str, float, int, list[str | float | int]], True],

                "release_date": [[str], False],
                "language": [[str], True],
                "translations": [[list[str]], False],
                "link": [[str], False],
                "tags": [[list[str]], False],
                "logo": [[str], False],
                "install_banner": [[str], False],
                "screenshots": [[list], False],
                "change_log": [[str], False],
                "other_info": [[str], False],
                "patcher_options": [[dict], False],
                "optional_content": [[list], False],
                "no_base_content": [[bool, str], False],
            }

            schema_prereqs = {
                "name": [[str, list[str]], True],
                "versions": [[list[str | int | float]], False],
                "optional_content": [[list[str]], False]
            }
            schema_patcher_options = {
                "gravity": [[float], False, [-100.0, -1.0]],
                "skins_in_shop": [[int], False, [8, 32]],
                "blast_damage_friendly_fire": [[bool, str], False, None],
                "game_font": [[str], False]
            }
            schema_optional_content = {
                "name": [[str], True],
                "display_name": [[str], True],
                "description": [[str], True],

                "default_option": [[str], False],
                "install_settings": [[list], False],
            }
            schema_install_settins = {
                "name": [[str], True],
                "description": [[str], True],
            }
            validated = Mod.validate_dict(install_config, schema_fieds_top)
            if validated:
                display_name = install_config.get("display_name")
                logger.info("***")
                logger.info(f"Initial mod '{display_name}' validation result: True")
                patcher_options = install_config.get("patcher_options")
                optional_content = install_config.get("optional_content")
                prerequisites = install_config.get("prerequisites")
                incompatibles = install_config.get("incompatible")
                if patcher_options is not None:
                    validated &= Mod.validate_dict_constrained(patcher_options, schema_patcher_options)
                    logger.info(f"Patcher options for mod '{display_name}' validation result: {validated}")

                if prerequisites is not None:
                    has_forbidden_prerequisites = False
                    for prereq_entry in prerequisites:
                        validated &= Mod.validate_dict(prereq_entry, schema_prereqs)
                        if validated:
                            if isinstance(prereq_entry.get("name"), str):
                                prereq_entry_checked = [prereq_entry["name"]]
                            else:
                                prereq_entry_checked = prereq_entry["name"]
                            entry_optional_content = prereq_entry.get("optional_content")
                            has_forbidden_prerequisites |= ("community_patch" in prereq_entry_checked
                                                            and bool(entry_optional_content)
                                                            and entry_optional_content is not None)
                    if has_forbidden_prerequisites:
                        logger.error("Prerequisites which include ComPatch can't specify optional content")
                    validated &= not has_forbidden_prerequisites
                    logger.info(f"Prerequisites for mod '{display_name}' validation result: {validated}")

                if incompatibles is not None:
                    has_forbidden_icompabilities = False
                    for incompatible_entry in incompatibles:
                        validated &= Mod.validate_dict(incompatible_entry, schema_prereqs)
                        if validated:
                            if isinstance(incompatible_entry.get("name"), str):
                                incompatible_entry_checked = [incompatible_entry["name"]]
                            else:
                                incompatible_entry_checked = incompatible_entry["name"]
                            has_forbidden_icompabilities |= bool(set(incompatible_entry_checked)
                                                                 & set(["community_patch"]))
                    if has_forbidden_icompabilities:
                        logger.error("Incompatibles can't contain ComPatch, should just have ComRem prereq")
                    validated &= not has_forbidden_icompabilities
                    logger.info(f"Incompatible content for mod '{display_name}' "
                                f"validation result: {validated}")

                if optional_content is not None:
                    validated &= Mod.validate_list(optional_content, schema_optional_content)
                    logger.info(f"Optional content for mod '{display_name}' validation result: {validated}")
                    if validated:
                        for option in optional_content:
                            if option.get("name") in ["base", "display_name", "build", "version"]:
                                validated = False
                                logger.error(f"Optional content name '"
                                            f"{option.get('name')}' of mod '{display_name}' "
                                            f"is one of the reserved system names, can't load mod properly!")
                            install_settings = option.get("install_settings")
                            if install_settings is not None:
                                validated &= (len(install_settings) > 1)
                                logger.info(f"Complex install settings num > 1 for content '"
                                            f"{option.get('name')}' of mod '{display_name}' "
                                            f"validation result: {validated}")
                                validated &= Mod.validate_list(install_settings, schema_install_settins)
                                logger.info(f"Install settings for content '{option.get('name')}' "
                                            f"of mod '{display_name}' validation result: {validated}")
                            patcher_options_additional = option.get('patcher_options')
                            if patcher_options_additional is not None:
                                validated &= Mod.validate_dict_constrained(patcher_options_additional,
                                                                           schema_patcher_options)
                                logger.info(f"Patcher options for additional content of the mod "
                                            f"'{display_name}' validation result: {validated}")

                if not skip_data_validation:
                    # community remaster is a mod, but it has a special folder name, we handle it here
                    if install_config.get("name") == "community_remaster":
                        mod_identifier = "remaster"
                    else:
                        mod_identifier = install_config.get("name")

                    if not install_config.get("no_base_content"):
                        validated_data_dir = os.path.isdir(os.path.join(mod_path, mod_identifier, "data"))
                        validated &= validated_data_dir
                        if not validated_data_dir:
                            logger.error('Expected path not exists: '
                                         f'{os.path.join(mod_path, mod_identifier, "data")}')
                        else:
                            logger.info(f"Mod '{display_name}' data folder validation result: "
                                        f"{validated_data_dir}")
                    if optional_content is not None:
                        for option in optional_content:
                            validated &= os.path.isdir(os.path.join(mod_path,
                                                                    mod_identifier,
                                                                    option.get("name")))
                            if option.get("install_settings") is not None:
                                for setting in option.get("install_settings"):
                                    validated &= os.path.isdir(os.path.join(mod_path,
                                                                            mod_identifier,
                                                                            option.get("name"),
                                                                            setting.get("name")))
                                    logger.info(f"Mod '{display_name}' optional content "
                                                f"'{option.get('name')}' setting '{setting.get('name')}' "
                                                f"folder validation result: {validated}")
                            logger.info(f"Mod '{display_name}' optional content '{option.get('name')}' "
                                        f"data folder validation result: {validated}")

            return validated
        else:
            logger.error("Broken config encountered, couldn't be read as dictionary")
            return False

    def compatible_with_mod_manager(self, patcher_version: str | float) -> bool:
        compatible = True

        patcher_version_parsed = Mod.Version(patcher_version)
        patcher_version_parsed.identifier = None
        error_msg = ""
        mod_manager_too_new = False

        for version in self.patcher_version_requirement:
            if ">=" == version[:2]:
                compare_operation = operator.ge
            elif "<=" == version[:2]:
                compare_operation = operator.le
            elif ">" == version[:1]:
                compare_operation = operator.gt
            elif "<" == version[:1]:
                compare_operation = operator.lt
            elif "=" == version[:1]:
                compare_operation = operator.eq
            else:  # default "version" treated the same as ">=version":
                compare_operation = operator.ge

            for sign in (">", "<", "="):
                version = version.replace(sign, '')

            parsed_required_ver = Mod.Version(version)
            parsed_required_ver.identifier = None

            if compare_operation is operator.eq and parsed_required_ver < patcher_version_parsed:
                mod_manager_too_new = True

            compatible &= compare_operation(patcher_version_parsed, parsed_required_ver)

        if not compatible:
            logger.warning(f"{self.display_name} manifest asks for an other mod manager version. "
                           f"Required: {self.patcher_version_requirement}, available: {patcher_version}")
            and_word = f" {tr('and')} "

            error_msg = (tr("usupported_patcher_version",
                            content_name=fconsole(self.display_name, bcolors.WARNING),
                            required_version=and_word.join(self.patcher_version_requirement),
                            current_version=patcher_version,
                            github_url=fconsole(COMPATCH_GITHUB, bcolors.HEADER)))

            if mod_manager_too_new and self.name == "community_remaster":
                error_msg += f"\n\n{tr('check_for_a_new_version')}\n\n"
                error_msg += tr("demteam_links",
                                discord_url=fconsole(DEM_DISCORD, bcolors.HEADER),
                                deuswiki_url=fconsole(WIKI_COMPATCH, bcolors.HEADER),
                                github_url=fconsole(COMPATCH_GITHUB, bcolors.HEADER)) + "\n"

        return compatible, error_msg.strip()

    @staticmethod
    def validate_dict(validating_dict: dict, scheme: dict) -> bool:
        '''Validates dictionary based on scheme in a format
           {name: [list of possible types, required(bool)]}.
           Supports generics for type checking in schemes'''
        # logger.debug(f"Validating dict with scheme {scheme.keys()}")
        if not isinstance(validating_dict, dict):
            logger.error(f"Validated part of scheme is not a dict: {validating_dict}")
            return False
        for field in scheme:
            types = scheme[field][0]
            required = scheme[field][1]
            value = validating_dict.get(field)
            if required and value is None:
                logger.error(f"key '{field}' is required but couldn't be found in manifest")
                return False
            elif required or (not required and value is not None):
                generics_present = any([hasattr(type_entry, "__origin__") for type_entry in types])
                if not generics_present:
                    valid_type = any([isinstance(value, type_entry) for type_entry in types])
                else:
                    valid_type = True
                    for type_entry in types:
                        if hasattr(type_entry, "__origin__"):
                            if isinstance(value, typing.get_origin(type_entry)):
                                if type(value) in [dict, list]:
                                    for value_internal in value:
                                        if not isinstance(value_internal, typing.get_args(type_entry)):
                                            valid_type = False
                                            break
                                else:
                                    valid_type = False
                                    break

                if not valid_type:
                    logger.error(f"key '{field}' has value {value} of invalid type '{type(value)}', "
                                 f"expected: {' or '.join(str(type_inst) for type_inst in types)}")
                    return False
        return True

    @staticmethod
    def validate_dict_constrained(validating_dict: dict, scheme: dict) -> bool:
        '''Validates dictionary based on scheme in a format
           {name: [list of possible types, required(bool), int or float value[min, max]]}.
           Doesn't support generics in schemes'''
        # logger.debug(f"Validating constrained dict with scheme {scheme.keys()}")
        for field in scheme:
            types = scheme[field][0]
            required = scheme[field][1]
            value = validating_dict.get(field)
            if (float in types) or (int in types):
                min_req = scheme[field][2][0]
                max_req = scheme[field][2][1]

            if required and value is None:
                logger.error(f"key '{field}' is required but couldn't be found in manifest")
                return False
            elif required or (not required and value is not None):
                valid_type = any([isinstance(value, type_entry) for type_entry in types])
                if not valid_type:
                    logger.error(f"key '{field}' is of invalid type '{type(field)}', expected '{types}'")
                    return False
                if float in types:
                    try:
                        value = float(value)
                    except ValueError:
                        logger.error(f"key '{field}' can't be converted to float as supported - "
                                     f"found value '{value}'")
                        return False
                if int in types:
                    try:
                        value = int(value)
                    except ValueError:
                        logger.error(f"key '{field}' can't be converted to int as supported - "
                                     f"found value '{value}'")
                        return False
                if ((float in types) or (int in types)) and (not (min_req <= value <= max_req)):
                    logger.error(f"key '{field}' is not in supported range '{min_req}-{max_req}'")
                    return False

        return True

    @staticmethod
    def validate_list(validating_list: list[dict], scheme: dict) -> bool:
        '''Runs validate_dict for multiple lists with the same scheme
           and returns total validation result for them'''
        # logger.debug(f"Validating list of length: '{len(validating_list)}'")
        to_validate = [element for element in validating_list if isinstance(element, dict)]
        result = all([Mod.validate_dict(element, scheme) for element in to_validate])
        # logger.debug(f"Result: {result}")
        return result

    def get_full_install_settings(self) -> dict:
        '''Returns settings that describe default installation of the mod'''
        install_settings = {}
        install_settings["base"] = "yes"
        if self.optional_content is not None:
            for option in self.optional_content:
                if option.default_option is not None:
                    install_settings[option.name] = option.default_option
                else:
                    install_settings[option.name] = "yes"
        return install_settings

    def get_install_description(self, install_config_original: dict) -> list[str]:
        '''Returns list of strings with localised description of the given mod installation config'''
        install_config = install_config_original.copy()

        descriptions = []

        base_part = install_config.pop("base")
        if base_part == 'yes':
            description = fconsole(f"{self.display_name}\n", bcolors.WARNING) + self.description
            descriptions.append(description)
        if len(install_config) > 0:
            ok_to_install = [entry for entry in install_config if install_config[entry] != 'skip']
            if len(ok_to_install) > 0:
                descriptions.append(f"{tr('including_options')}:")
        for mod_part in install_config:
            setting_obj = self.options_dict.get(mod_part)
            if install_config[mod_part] == "yes":
                description = (fconsole(f"* {setting_obj.display_name}\n", bcolors.OKBLUE)
                               + setting_obj.description)
                descriptions.append(description)
            elif install_config[mod_part] != "skip":
                description = (fconsole(f"* {setting_obj.display_name}\n", bcolors.OKBLUE)
                               + setting_obj.description)
                if setting_obj.install_settings is not None:
                    for setting in setting_obj.install_settings:
                        if setting.get("name") == install_config[mod_part]:
                            install_description = setting.get("description")
                            description += (f"\t** {tr('install_setting_title')}: "
                                            f"{install_description}")
                descriptions.append(description)
        return descriptions

    class Tags(Enum):
        BUGFIX = 0
        GAMEPLAY = 1
        STORY = 2
        VISUAL = 3
        AUDIO = 4
        WEAPONS = 5
        VEHICLES = 6
        UI = 7
        BALANCE = 8
        HUMOR = 9
        UNCATEGORIZED = 10

        @classmethod
        def list_values(cls):
            return list(map(lambda c: c.value, cls))

        @classmethod
        def list_names(cls):
            return list(map(lambda c: c.name, cls))

    @total_ordering
    class Version:
        def __init__(self, version_str: str) -> None:
            self.major = '0'
            self.minor = '0'
            self.patch = '0'
            self.identifier = ''

            identifier_index = version_str.find('-')
            has_minor_ver = "." in version_str

            if identifier_index != -1:
                self.identifier = version_str[identifier_index + 1:]
                numeric_version = version_str[:identifier_index]
            else:
                numeric_version = version_str

            if has_minor_ver:
                version_split = numeric_version.split('.')
                version_levels = len(version_split)
                if version_levels > 0:
                    self.major = version_split[0][:4]

                if version_levels > 1:
                    self.minor = version_split[1][:4]

                if version_levels > 2:
                    self.patch = version_split[2][:10]

                if version_levels > 3:
                    self.patch = ''.join(version_split[2:])
            else:
                self.major = numeric_version

            self.is_numeric = all([part.isnumeric() for part in [self.major, self.minor, self.patch]])

        def __str__(self) -> str:
            version = f"{self.major}.{self.minor}.{self.patch}"
            if self.identifier:
                version += f"-{self.identifier}"
            return version

        def __repr__(self) -> str:
            return str(self)

        def _is_valid_operand(self, other: typing.Any):
            return (isinstance(other, Mod.Version))

        def __eq__(self, other: Mod.Version) -> bool:
            if not self._is_valid_operand(other):
                return NotImplemented

            if self.is_numeric and other.is_numeric:
                return ((int(self.major), int(self.minor), int(self.patch))
                        ==
                        (int(other.major), int(other.minor), int(other.patch)))
            else:
                return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                        ==
                        (self.major.lower(), self.minor.lower(), self.patch.lower()))

        def __lt__(self, other: Mod.Version) -> bool:
            if not self._is_valid_operand(other):
                return NotImplemented

            if self.is_numeric and other.is_numeric:
                return ((int(self.major), int(self.minor), int(self.patch))
                        <
                        (int(other.major), int(other.minor), int(other.patch)))
            else:
                return ((self.major.lower(), self.minor.lower(), self.path.lower())
                        <
                        (self.major.lower(), self.minor.lower(), self.path.lower()))

    class OptionalContent:
        def __init__(self, description: dict, parent: Mod) -> None:
            self.name = str(description.get("name"))[:64].replace("/", "").replace("\\", "").replace(".", "")
            self.display_name = description.get("display_name")[:64]
            self.description = description.get("description")[:256].strip()

            self.install_settings = description.get("install_settings")
            self.default_option = None
            default_option = description.get("default_option")

            if self.install_settings is not None:
                for custom_setting in self.install_settings:
                    custom_setting["name"] = custom_setting["name"][:64].strip()
                    custom_setting["description"] = custom_setting["description"][:128].strip()
                if default_option in [opt["name"] for opt in self.install_settings]:
                    self.default_option = default_option
                elif isinstance(default_option, str):
                    if default_option.lower() == "skip":
                        self.default_option = "skip"
                elif default_option is None:
                    pass  # default behavior if default option is not specified
                else:
                    er_message = (f"Incorrect default option '{default_option}' "
                                  f"for '{self.name}' in content manifest! "
                                  f"Only 'skip' or names present in install settings are allowed")
                    logger.error(er_message)
                    raise KeyError(er_message)
            else:
                if isinstance(default_option, str):
                    if default_option.lower() == "skip":
                        self.default_option = "skip"
                    elif default_option.lower() == "install":
                        pass  # same as default
                    else:
                        er_message = (f"Incorrect default option '{default_option}' "
                                      f"for '{self.name}' in content manifest. "
                                      f"Only 'skip' or 'install' is allowed for simple options!")

            no_base_content = description.get("no_base_content")
            patcher_options = description.get("patcher_options")
            if patcher_options is not None:
                for option in patcher_options:
                    # optional content can overwrite base mode options
                    parent.patcher_options[option] = patcher_options[option]
            if no_base_content is not None:
                if isinstance(no_base_content, bool):
                    self.no_base_content = no_base_content
                else:
                    no_base_content = str(no_base_content)
                    if no_base_content.lower() == "true":
                        self.no_base_content = True
                    elif no_base_content.lower() == "false":
                        pass
                    else:
                        er_message = f"Broken manifest for content '{self.name}'!"
                        logger.error(er_message)
                        raise ValueError(er_message)
