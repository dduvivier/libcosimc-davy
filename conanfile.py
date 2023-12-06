import os

from conan import ConanFile
from conan.tools.cmake import CMake
from conan.tools.env import VirtualRunEnv
from conan.tools.env import VirtualBuildEnv
from conan.tools.cmake import CMakeToolchain, CMake, CMakeDeps, cmake_layout
from conan.tools.files import copy, load


class LibCosimCConan(ConanFile):
    # Basic package info
    name = "libcosimc"

    def set_version(self):
        self.version = load(self, os.path.join(self.recipe_folder, "version.txt")).strip()

    # Metadata
    license = "MPL-2.0"
    author = "osp"
    description = "A C wrapper for libcosim, a co-simulation library for C++"

    # Binary configuration
    package_type = "library"
    settings = "os", "compiler", "build_type", "arch"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
    }
    default_options = {
        "shared": True,
        "fPIC": True,
    }

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")
        self.options["*"].shared = self.options.shared

    # Dependencies/requirements
    tool_requires = (
        "cmake/[>=3.15]",
        "doxygen/[>=1.8]",
        "patchelf/[>=0.18]",
    )
    requires = (
        "libcosim/0.11.0",
        "boost/[>=1.71.0]",
    )

    # Exports
    exports = "version.txt"
    exports_sources = "*"

   # Build steps

    def layout(self):
        cmake_layout(self)
        
    def generate(self):
        # Copy dependencies to the folder where executables (tests, mainly)
        # will be placed, so it's easier to run them.
        bindir = os.path.join(
            self.build_folder,
            "output",
            str(self.settings.build_type).lower(),
            "bin")
        dldir = (bindir if self.settings.os == "Windows" else
            os.path.join(self.build_folder, "dist", "lib"))
        dependency_libs = {
            # For some dependencies, we only want a subset of the libraries
            "boost" : [
                "boost_atomic*",
                "boost_chrono*",
                "boost_container*",
                "boost_context*",
                "boost_date_time*",
                "boost_filesystem*",
                "boost_locale*",
                "boost_log*",
                "boost_log_setup*",
                "boost_program_options*",
                "boost_random*",
                "boost_regex*",
                "boost_serialization*",
                "boost_system*",
                "boost_thread*"],
            "thrift": ["thrift", "thriftd"],
        }
        for req, dep in self.dependencies.items():
            self._import_dynamic_libs(dep, dldir, dependency_libs.get(req.ref.name, ["*"]))
        if self.dependencies["libcosim"].options.proxyfmu:
            self._import_executables(self.dependencies["proxyfmu"], bindir, ["*"])

        # Generate build system
        CMakeToolchain(self).generate()
        CMakeDeps(self).generate()

 
    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()
        cmake.build(target="doc")
        if self._is_tests_enabled():
            env = VirtualRunEnv(self).environment()
            env.define("CTEST_OUTPUT_ON_FAILURE", "ON")
            with env.vars(self).apply():
                cmake.test()

    # Packaging
    def package(self):
        cmake = CMake(self)
        cmake.install()
        cmake.build(target="install-doc")

    def _import_dynamic_libs(self, dependency, target_dir, patterns):
        if dependency.options.get_safe("shared", False):
            if self.settings.os == "Windows":
                depdirs = dependency.cpp_info.bindirs
            else:
                depdirs = dependency.cpp_info.libdirs
            for depdir in depdirs:
                for pattern in patterns:
                    patternx = pattern+".dll" if self.settings.os == "Windows" else "lib"+pattern+".so*"
                    files = copy(self, patternx, depdir, target_dir, keep_path=False)
                    self._update_rpath(files, "$ORIGIN")

    def _import_executables(self, dependency, target_dir, patterns=["*"]):
        for bindir in dependency.cpp_info.bindirs:
            for pattern in patterns:
                patternx = pattern+".exe" if self.settings.os == "Windows" else pattern
                files = copy(self, patternx, bindir, target_dir, keep_path=False)
                self._update_rpath(files, "$ORIGIN/../lib")

    def _update_rpath(self, files, new_rpath):
        if files and self.settings.os == "Linux":
            with VirtualBuildEnv(self).environment().vars(self).apply():
                self.run("patchelf --set-rpath '" + new_rpath + "' '" + ("' '".join(files)) + "'")

    def package_info(self):
        self.cpp_info.libs = [ "cosimc" ]
        # Ensure that consumers use our CMake package configuration files
        # rather than ones generated by Conan.
        self.cpp_info.set_property("cmake_find_mode", "none")
        self.cpp_info.builddirs.append(".")

    # Helper functions
    def _is_tests_enabled(self):
        return os.getenv("LIBCOSIMC_RUN_TESTS_ON_CONAN_BUILD", "False").lower() in ("true", "1")
