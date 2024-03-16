import logging
from pathlib import Path
from zipfile import ZipInfo

from py7zr import py7zr

from commod.game.mod import Mod

logger = logging.getLogger("dem")

def validate_archive_mod_paths(
        mod: Mod,
        mod_config_path: str,
        archive_file_list: list[ZipInfo] | py7zr.ArchiveFileList) -> bool:

    validated = True

    if isinstance(archive_file_list, py7zr.ArchiveFileList):
        archive_files = []
        for file in archive_file_list:
            if file.emptystream:
                archive_files.append(f"{file.filename}/")
            else:
                archive_files.append(file.filename)
    elif isinstance(archive_file_list, list[ZipInfo]):
        archive_files = [file.filename for file in archive_file_list]
    else:
        raise NotImplementedError("Wrong archive type passed to validator")

    if not mod.no_base_content:
        mod_base_paths: list[Path] = []
        if mod.data_dirs:
            # TODO: check that using Path instead of str is not breaking checks here
            mod_base_paths = [Path(mod_config_path).parent / base_dir for base_dir in mod.data_dirs]
        else:
            mod_base_paths.append(Path(mod_config_path).parent / "data")

        if mod.bin_dirs:
            mod_base_paths.extend(Path(mod_config_path).parent / bin_dir for bin_dir in mod.bin_dirs)

        data_dir_validated = all(base_path in archive_files for base_path in mod_base_paths)
        validated &= data_dir_validated
        if data_dir_validated:
            logger.info("\tPASS: Archived base mod data folder validation result")
        else:
            logger.error("\tFAIL: Archived base mod data folder validation fail, "
                         f"expected path not found: {mod_base_paths}")

    if not validated:
        logger.info("<! BASE FILES VALIDATION FAILED, SKIPPING FURTHER CHECKS !>")
        return validated

    if self.optional_content:
        for option in self.optional_content:
            validated &= mod_config_path.replace(
                "manifest.yaml", f'{self.options_base_dir}{option.get("name")}/') in archive_files
            if option.get("install_settings") is not None:
                for setting in option.get("install_settings"):
                    validated &= mod_config_path.replace(
                        "manifest.yaml",
                        f'{option.get("name")}/{setting.get("name")}/data/') in archive_files
                    logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                                f"Archived optional content '{option.get('name')}' "
                                f"install setting '{setting.get('name')}' "
                                f"data folder validation result")
            else:
                validated &= mod_config_path.replace(
                    "manifest.yaml", f'{option.get("name")}/data/') in archive_files
            logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                        f"Archived optional content '{option.get('name')}' "
                        "data folder validation result")
    return validated
