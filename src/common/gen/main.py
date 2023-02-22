#!/usr/bin/python3

from argparse import ArgumentParser
from glob import glob
from os import R_OK, W_OK, X_OK, access, getenv, path, remove, unlink
from os.path import exists, isdir, isfile, islink
from shutil import rmtree
from subprocess import DEVNULL, STDOUT, run
from sys import exit as sys_exit, path as sys_path
from time import sleep
from traceback import format_exc


sys_path.extend(
    (
        "/usr/share/bunkerweb/deps/python",
        "/usr/share/bunkerweb/utils",
        "/usr/share/bunkerweb/api",
    )
)

from logger import setup_logger
from Configurator import Configurator
from Templator import Templator


if __name__ == "__main__":
    logger = setup_logger("Generator", getenv("LOG_LEVEL", "INFO"))
    wait_retry_interval = int(getenv("WAIT_RETRY_INTERVAL", "5"))

    try:
        # Parse arguments
        parser = ArgumentParser(description="BunkerWeb config generator")
        parser.add_argument(
            "--settings",
            default="/usr/share/bunkerweb/settings.json",
            type=str,
            help="file containing the main settings",
        )
        parser.add_argument(
            "--templates",
            default="/usr/share/bunkerweb/confs",
            type=str,
            help="directory containing the main template files",
        )
        parser.add_argument(
            "--core",
            default="/usr/share/bunkerweb/core",
            type=str,
            help="directory containing the core plugins",
        )
        parser.add_argument(
            "--plugins",
            default="/etc/bunkerweb/plugins",
            type=str,
            help="directory containing the external plugins",
        )
        parser.add_argument(
            "--output",
            default="/etc/nginx",
            type=str,
            help="where to write the rendered files",
        )
        parser.add_argument(
            "--target",
            default="/etc/nginx",
            type=str,
            help="where nginx will search for configurations files",
        )
        parser.add_argument(
            "--variables",
            type=str,
            help="path to the file containing environment variables",
        )
        args = parser.parse_args()

        logger.info("Generator started ...")
        logger.info(f"Settings : {args.settings}")
        logger.info(f"Templates : {args.templates}")
        logger.info(f"Core : {args.core}")
        logger.info(f"Plugins : {args.plugins}")
        logger.info(f"Output : {args.output}")
        logger.info(f"Target : {args.target}")

        integration = "Linux"
        if getenv("KUBERNETES_MODE", "no") == "yes":
            integration = "Kubernetes"
        elif getenv("SWARM_MODE", "no") == "yes":
            integration = "Swarm"
        elif getenv("AUTOCONF_MODE", "no") == "yes":
            integration = "Autoconf"
        elif exists("/usr/share/bunkerweb/INTEGRATION"):
            with open("/usr/share/bunkerweb/INTEGRATION", "r") as f:
                integration = f.read().strip()

        if args.variables:
            logger.info(f"Variables : {args.variables}")

            # Check existences and permissions
            logger.info("Checking arguments ...")
            files = [args.settings, args.variables]
            paths_rx = [args.core, args.plugins, args.templates]
            paths_rwx = [args.output]
            for file in files:
                if not path.exists(file):
                    logger.error(f"Missing file : {file}")
                    sys_exit(1)
                if not access(file, R_OK):
                    logger.error(f"Can't read file : {file}")
                    sys_exit(1)
            for _path in paths_rx + paths_rwx:
                if not path.isdir(_path):
                    logger.error(f"Missing directory : {_path}")
                    sys_exit(1)
                if not access(_path, R_OK | X_OK):
                    logger.error(
                        f"Missing RX rights on directory : {_path}",
                    )
                    sys_exit(1)
            for _path in paths_rwx:
                if not access(_path, W_OK):
                    logger.error(
                        f"Missing W rights on directory : {_path}",
                    )
                    sys_exit(1)

            # Compute the config
            logger.info("Computing config ...")
            config = Configurator(
                args.settings, args.core, args.plugins, args.variables, logger
            )
            config = config.get_config()
        else:
            sys_path.append("/usr/share/bunkerweb/db")
            from Database import Database

            db = Database(
                logger,
                sqlalchemy_string=getenv("DATABASE_URI", None),
            )
            config = db.get_config()

        # Remove old files
        logger.info("Removing old files ...")
        files = glob(f"{args.output}/*")
        for file in files:
            if islink(file):
                unlink(file)
            elif isfile(file):
                remove(file)
            elif isdir(file):
                rmtree(file, ignore_errors=False)

        # Render the templates
        logger.info("Rendering templates ...")
        templator = Templator(
            args.templates,
            args.core,
            args.plugins,
            args.output,
            args.target,
            config,
        )
        templator.render()

        if integration == "Linux":
            retries = 0
            while not exists("/var/tmp/bunkerweb/nginx.pid"):
                if retries == 5:
                    logger.error(
                        "BunkerWeb's nginx didn't start in time.",
                    )
                    sys_exit(1)

                logger.warning(
                    "Waiting for BunkerWeb's nginx to start, retrying in 5 seconds ...",
                )
                retries += 1
                sleep(5)

            proc = run(["nginx", "-s", "reload"], stdin=DEVNULL, stderr=STDOUT)
            if proc.returncode != 0:
                status = 1
                logger.error("Error while reloading nginx")
            else:
                logger.info("Successfully reloaded nginx")

    except SystemExit as e:
        sys_exit(e)
    except:
        logger.error(
            f"Exception while executing generator : {format_exc()}",
        )
        sys_exit(1)

    # We're done
    logger.info("Generator successfully executed !")