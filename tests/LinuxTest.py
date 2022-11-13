from Test import Test
from os.path import isdir, isfile
from os import getenv, mkdir, chmod
from shutil import rmtree
from traceback import format_exc
from subprocess import run
from time import sleep
from logger import setup_logger


class LinuxTest(Test):
    def __init__(self, name, timeout, tests, distro):
        super().__init__(name, "linux", timeout, tests)
        self._domains = {
            r"www\.example\.com": getenv("TEST_DOMAIN1"),
            r"auth\.example\.com": getenv("TEST_DOMAIN1"),
            r"app1\.example\.com": getenv("TEST_DOMAIN1_1"),
            r"app2\.example\.com": getenv("TEST_DOMAIN1_2"),
            r"app3\.example\.com": getenv("TEST_DOMAIN1_3"),
        }
        if not distro in ["ubuntu", "debian", "fedora", "centos"]:
            raise Exception(f"unknown distro {distro}")
        self.__distro = distro
        self.__logger = setup_logger("Linux_test", getenv("LOGLEVEL", "INFO"))

    @staticmethod
    def init(distro):
        try:
            if not Test.init():
                return False
            # TODO : find the nginx uid/gid on Docker images
            proc = run("sudo chown -R root:root /tmp/bw-data", shell=True)
            if proc.returncode != 0:
                raise Exception("chown failed (autoconf stack)")
            if isdir("/tmp/linux"):
                rmtree("/tmp/linux")
            mkdir("/tmp/linux")
            chmod("/tmp/linux", 0o0777)
            cmd = f"docker run -p 80:80 -p 443:443 --rm --name linux-{distro} -d --tmpfs /tmp --tmpfs /run --tmpfs /run/lock -v /sys/fs/cgroup:/sys/fs/cgroup:ro bw-{distro}"
            proc = run(cmd, shell=True)
            if proc.returncode != 0:
                raise Exception("docker run failed (linux stack)")
            if distro in ["ubuntu", "debian"]:
                cmd = "apt install -y /opt/\$(ls /opt | grep deb)"
            elif distro in ["centos", "fedora"]:
                cmd = "dnf install -y /opt/\$(ls /opt | grep rpm)"
            proc = LinuxTest.docker_exec(distro, cmd)
            if proc.returncode != 0:
                raise Exception("docker exec apt install failed (linux stack)")
            proc = LinuxTest.docker_exec(distro, "systemctl start bunkerweb")
            if proc.returncode != 0:
                raise Exception("docker exec systemctl start failed (linux stack)")
            cp_dirs = {
                "/tmp/bw-data/letsencrypt": "/etc/letsencrypt",
                "/tmp/bw-data/cache": "/var/cache/bunkerweb",
            }
            for src, dst in cp_dirs.items():
                proc = LinuxTest.docker_cp(distro, src, dst)
                if proc.returncode != 0:
                    raise Exception(f"docker cp failed for {src} (linux stack)")
                proc = LinuxTest.docker_exec(distro, f"chown -R nginx:nginx {dst}/*")
                if proc.returncode != 0:
                    raise Exception(
                        f"docker exec failed for directory {src} (linux stack)"
                    )

            if distro in ["ubuntu", "debian"]:
                LinuxTest.docker_exec(
                    distro,
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y php-fpm unzip",
                )
                if distro == "ubuntu":
                    LinuxTest.docker_cp(
                        distro,
                        "./tests/www-deb.conf",
                        "/etc/php/8.1/fpm/pool.d/www.conf",
                    )
                    LinuxTest.docker_exec(
                        distro, "systemctl stop php8.1-fpm ; systemctl start php8.1-fpm"
                    )
                elif distro == "debian":
                    LinuxTest.docker_cp(
                        distro,
                        "./tests/www-deb.conf",
                        "/etc/php/7.4/fpm/pool.d/www.conf",
                    )
                    LinuxTest.docker_exec(
                        distro, "systemctl stop php7.4-fpm ; systemctl start php7.4-fpm"
                    )
            elif distro in ["centos", "fedora"]:
                LinuxTest.docker_exec(distro, "dnf install -y php-fpm unzip")
                LinuxTest.docker_cp(
                    distro, "./tests/www-rpm.conf", "/etc/php-fpm.d/www.conf"
                )
                LinuxTest.docker_exec(
                    distro,
                    "mkdir /run/php ; chmod 777 /run/php ; systemctl stop php-fpm ; systemctl start php-fpm",
                )
            sleep(60)
        except:
            setup_logger("Linux_test", getenv("LOGLEVEL", "INFO")).error(
                f"exception while running LinuxTest.init()\n{format_exc()}",
            )
            return False
        return True

    @staticmethod
    def end(distro):
        ret = True
        try:
            if not Test.end():
                return False
            proc = run(f"docker kill linux-{distro}", shell=True)
            if proc.returncode != 0:
                ret = False
        except:
            setup_logger("Linux_test", getenv("LOGLEVEL", "INFO")).error(
                f"exception while running LinuxTest.end()\n{format_exc()}"
            )
            return False
        return ret

    def _setup_test(self):
        try:
            super()._setup_test()
            test = f"/tmp/tests/{self._name}"
            for ex_domain, test_domain in self._domains.items():
                Test.replace_in_files(test, ex_domain, test_domain)
                Test.rename(test, ex_domain, test_domain)
            Test.replace_in_files(test, "example.com", getenv("ROOT_DOMAIN"))
            proc = LinuxTest.docker_cp(self.__distro, test, f"/opt/{self._name}")
            if proc.returncode != 0:
                raise Exception("docker cp failed (test)")
            setup = test + "/setup-linux.sh"
            if isfile(setup):
                proc = LinuxTest.docker_exec(
                    self.__distro, f"cd /opt/{self._name} && ./setup-linux.sh"
                )
                if proc.returncode != 0:
                    raise Exception("docker exec setup failed (test)")
            proc = LinuxTest.docker_exec(
                self.__distro, f"cp /opt/{self._name}/variables.env /etc/bunkerweb/"
            )
            if proc.returncode != 0:
                raise Exception("docker exec cp variables.env failed (test)")
            proc = LinuxTest.docker_exec(
                self.__distro, "systemctl stop bunkerweb ; systemctl start bunkerweb"
            )
            if proc.returncode != 0:
                raise Exception("docker exec systemctl restart failed (linux stack)")
        except:
            self.__logger.error(
                f"exception while running LinuxTest._setup_test()\n{format_exc()}",
            )
            self._debug_fail()
            self._cleanup_test()
            return False
        return True

    def _cleanup_test(self):
        try:
            proc = LinuxTest.docker_exec(
                self.__distro,
                f"cd /opt/{self._name} ; ./cleanup-linux.sh ; rm -rf /etc/bunkerweb/configs/* ; rm -rf /etc/bunkerweb/plugins/*",
            )
            if proc.returncode != 0:
                raise Exception("docker exec rm failed (cleanup)")
            super()._cleanup_test()
        except:
            self.__logger.error(
                f"exception while running LinuxTest._cleanup_test()\n{format_exc()}",
            )
            return False
        return True

    def _debug_fail(self):
        LinuxTest.docker_exec(
            self.__distro,
            "cat /var/log/nginx/access.log ; cat /var/log/nginx/error.log ; journalctl -u bunkerweb --no-pager",
        )

    def docker_exec(distro, cmd_linux):
        return run(
            f'docker exec linux-{distro} /bin/bash -c "{cmd_linux}"',
            shell=True,
        )

    def docker_cp(distro, src, dst):
        return run(f"sudo docker cp {src} linux-{distro}:{dst}", shell=True)