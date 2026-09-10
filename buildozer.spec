# This .spec config file tells Buildozer an app's requirements for being built.
#
# It largely follows the syntax of an .ini file.
# See the end of the file for more details and warnings about common mistakes.

[app]

# (str) Title of your application
title = 北斗发送端

# (str) Package name
package.name = beidousender

# (str) Package domain (needed for android/ios packaging)
package.domain = org.beidou

# (str) Source code where the main.py live
source.dir = .
main.py = main.py
# (list) Source files to include (leave empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas

# (list) List of inclusions using pattern matching
#source.include_patterns = assets/*,images/*.png

# (list) Source files to exclude (leave empty to not exclude anything)
#source.exclude_exts = spec

# (list) List of directory to exclude (leave empty to not exclude anything)
#source.exclude_dirs = tests, bin, venv

# (list) List of exclusions using pattern matching
# Do not prefix with './'
#source.exclude_patterns = license,images/*/*.jpg

# (str) Application versioning (method 1)
version = 0.1

# (str) Application versioning (method 2)
# version.regex = __version__ = ['"](.*)['"]
# version.filename = %(source.dir)s/main.py

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3,kivy,usb4a,pyjnius
android.permissions = INTERNET, (name=android.permission.WRITE_EXTERNAL_STORAGE;maxSdkVersion=18)
#android.features = android.hardware.usb.host

# (str) Custom source folders for requirements
# Sets custom source for any requirements with recipes
# requirements.source.kivy = ../../kivy

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/data/icon.png

# (list) Supported orientations
# Valid options are: landscape, portrait, portrait-reverse, landscape-reverse, or all
orientation = portrait

# (list) List of services to declare
#services = NAME:ENTRYPOINT_TO_PY,NAME2:ENTRYPOINT2_TO_PY

#
# OSX Specific
#

#
# author = © Copyright Info

# Kivy version to use
osx.kivy_version = 2.2.0

#
# Android specific
#

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (string) Presplash background color (for android toolchain)
#android.presplash_color = #FFFFFF

# (string) Presplash animation using Lottie format.
#android.presplash_lottie = "path/to/lottie/file.json"

# (str) Adaptive icon of the application (used if Android API level is 26+ at runtime)
#icon.adaptive_foreground.filename = %(source.dir)s/data/icon_fg.png
#icon.adaptive_background.filename = %(source.dir)s/data/icon_bg.png

# (list) Permissions
#android.permissions = android.permission.INTERNET, (name=android.permission.WRITE_EXTERNAL_STORAGE;maxSdkVersion=18)

# (list) features (adds uses-feature -tags to manifest)
#android.features = android.hardware.usb.host

# (int) Target Android API, should be as high as possible.
android.api = 33
#android.python_version = 3.11.8

# (int) Minimum API your APK / AAB will support.
android.minapi = 24

# (int) Android SDK version to use
#android.sdk = 20

# (str) Android NDK version to use
android.ndk = 26c

# (int) Android NDK API to use. This is the minimum API your app will support, it should usually match android.minapi.
#android.ndk_api = 21

# (str) Android NDK directory (if empty, it will be automatically downloaded.)
#android.ndk_path =

# (str) Android SDK directory (if empty, it will be automatically downloaded.)
#android.sdk_path =

# (str) ANT directory (if empty, it will be automatically downloaded.)
#android.ant_path =

# (bool) If True, then skip trying to update the Android SDK
# android.skip_update = False

# (bool) If True, then automatically accept SDK license
# agreements.
android.accept_sdk_license = True

# (str) Android entry point, default is ok for Kivy-based app
#android.entrypoint = org.kivy.android.PythonActivity

# (str) Full name including package path of the Java class that implements Android Activity
#android.activity_class_name = org.kivy.android.PythonActivity

# (str) Extra xml to write directly inside the <manifest> element of AndroidManifest.xml
android.extra_manifest_xml = ./usb_feature.xml

# (str) Extra xml to write directly inside the <manifest><application> tag of AndroidManifest.xml
#android.extra_manifest_application_arguments = ./src/android/extra_manifest_application_arguments.xml

# (str) Full name including package path of the Java class that implements Python Service
#android.service_class_name = org.kivy.android.PythonService

# (str) Android app theme, default is ok for Kivy-based app
# android.apptheme = "@android:style/Theme.NoTitleBar"

# (list) Pattern to whitelist for the whole project
#android.whitelist =

# (bool) If True, your application will be listed as a home app (launcher app)
# android.home_app = False

# (str) Path to a custom whitelist file
#android.whitelist_src =

# (str) Path to a custom blacklist file
#android.blacklist_src =

# (list) List of Java .jar files to add to the libs so that pyjnius can access
#android.add_jars = foo.jar,bar.jar,path/to/more/*.jar

# (list) List of Java files to add to the android project (can be java or a directory)
#android.add_src =

# (list) Android AAR archives to add
#android.add_aars =

# (list) Put these files or directories in the apk assets directory.
#android.add_assets =

# (list) Put these files or directories in the apk res directory.
#android.add_resources =

# (list) Gradle dependencies to add
#android.gradle_dependencies =

# (bool) Enable AndroidX support.
#android.enable_androidx = True

# (list) add java compile options
# android.add_compile_options = "sourceCompatibility = 1.8", "targetCompatibility = 1.8"

# (list) Gradle repositories to add
#android.add_gradle_repositories =

# (list) packaging options to add
#android.add_packaging_options =

# (list) Java classes to add as activities to the manifest.
#android.add_activities = com.example.ExampleActivity

# (str) OUYA Console category.
#android.ouya.category = GAME

# (str) Filename of OUYA Console icon.
#android.ouya.icon.filename = %(source.dir)s/data/ouya_icon.png

# (str) XML file to include as an intent filters in <activity> tag
#android.manifest.intent_filters =

# (list) Copy these files to src/main/res/xml/
#android.res_xml = PATH_TO_FILE,

# (str) launchMode to set for the main activity
#android.manifest.launch_mode = standard

# (str) screenOrientation to set for the main activity.
#android.manifest.orientation = fullSensor

# (list) Android additional libraries to copy into libs/armeabi
#android.add_libs_armeabi = libs/android/*.so
#android.add_libs_armeabi_v7a = libs/android-v7/*.so
#android.add_libs_arm64_v8a = libs/android-v8/*.so
#android.add_libs_x86 = libs/android-x86/*.so
#android.add_libs_mips = libs/android-mips/*.so

# (bool) Indicate whether the screen should stay on
#android.wakelock = False

# (list) Android application meta-data to set (key=value format)
#android.meta_data =

# (list) Android library project to add
#android.library_references =

# (list) Android shared libraries which will be added to AndroidManifest.xml using <uses-library> tag
#android.uses_library =

# (str) Android logcat filters to use
#android.logcat_filters = *:S python:D

# (bool) Android logcat only display log for activity's pid
#android.logcat_pid_only = False

# (str) Android additional adb arguments
#android.adb_args = -H host.docker.internal

# (bool) Copy library instead of making a libpymodules.so
#android.copy_libs = 1

# (list) The Android archs to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a

# (int) overrides automatic versionCode computation
# android.numeric_version = 1

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

# (str) XML file for custom backup rules
# android.backup_rules =

# (str) If you need to insert variables into your AndroidManifest.xml file,
# android.manifest_placeholders = [:]

# (bool) Skip byte compile for .py files
# android.no-byte-compile-python = False

# (str) The format used to package the app for release mode (aab or apk or aar).
# android.release_artifact = aab

# (str) The format used to package the app for debug mode (apk or aar).
# android.debug_artifact = apk

# (str) A display cutout is an area on some devices that extends into the display surface.
#android.display_cutout = never

#
# Python for android (p4a) specific
#

# (str) python-for-android URL to use for checkout
#p4a.url =

# (str) python-for-android fork to use in case if p4a.url is not specified, defaults to upstream (kivy)
p4a.fork = kivy

# (str) python-for-android branch to use, defaults to master
p4a.branch = master

# (str) python-for-android specific commit to use, defaults to HEAD, must be within p4a.branch
#p4a.commit = HEAD

# (str) python-for-android git clone directory
#p4a.source_dir =

# (str) The directory in which python-for-android should look for your own build recipes (if any)
# p4a.local_recipes = ./recipes

# (str) Filename to the hook for p4a
#p4a.hook =

# (str) Bootstrap to use for android builds
# p4a.bootstrap = sdl2

# (int) port number to specify an explicit --port= p4a argument
#p4a.port =

# Control passing the --use-setup-py vs --ignore-setup-py to p4a
#p4a.setup_py = false

# (str) extra command line arguments to pass when invoking pythonforandroid.toolchain
#p4a.extra_args = --no-binary :all:

#
# iOS specific
#

# (str) Path to a custom kivy-ios folder
#ios.kivy_ios_dir = ../kivy-ios
# Alternately, specify the URL and branch of a git checkout:
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

# Another platform dependency: ios-deploy
#ios.ios_deploy_dir = ../ios_deploy
# Or specify URL and branch
ios.ios_deploy_url = https://github.com/phonegap/ios-deploy
ios.ios_deploy_branch = 1.12.2

# (bool) Whether or not to sign the code
ios.codesign.allowed = false

# (str) Name of the certificate to use for signing the debug version
#ios.codesign.debug = "iPhone Developer: <lastname> <firstname> (<hexstring>)"

# (str) The development team to use for signing the debug version
#ios.codesign.development_team.debug = <hexstring>

# (str) Name of the certificate to use for signing the release version
#ios.codesign.release = %(ios.codesign.debug)s

# (str) The development team to use for signing the release version
#ios.codesign.development_team.release = <hexstring>

# (str) Justification text to be provided for being able to select media
#ios.media_usage_description = "<APP> needs to access your media in order to <Do X and Y and Z> "

# (str) Justification text to be provided for being able to use local network
#ios.local_network_usage_description = "<App> needs permissions to <Do X and Y and Z> in your Local Area Network"

# (str) Camera Usage justification string.
#ios.camera_usage_description = "<App> uses Camera to do <X and Y and Z>"

# (bool) Allow StatusBar to be controlled by API
# ios.viewcontroller_based_statusbar_appearance = False

# (str) A Xml String specifying a extension type.
#ios.app_extensions = [["7zip", "zip"],  ["public.zip-archive"], "org.kivy.myappextensionfile", "<MyCustom> Extension File", "${MACOSX_BUNDLE_ICON_FILE}", "http://mysite.com/myapp/extensions.html"],

# (str) URL pointing to .ipa file to be installed
#ios.manifest.app_url =

# (str) URL pointing to an icon (57x57px) to be displayed during download
#ios.manifest.display_image_url =

# (str) URL pointing to a large icon (512x512px) to be used by iTunes
#ios.manifest.full_size_image_url =


[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1

# (str) Path to build artifact storage, absolute or relative to spec file
# build_dir = ./.buildozer

# (str) Path to build output (i.e. .apk, .aab, .ipa) storage
# bin_dir = ./bin

#-----------------------------------------------------------------------------
#   Notes about using this file:
#
#   Buildozer uses a variant of Python's ConfigSpec to read this file.
#   For the basic syntax, including interpolations, see
#       https://docs.python.org/3/library/configparser.html#supported-ini-file-structure
#
#   Warning: Comments cannot be used "inline" - i.e.
#       [app]
#       title = My Application # This is not a comment, it is part of the title.
#
#   Warning: Indented text is treated as a multiline string - i.e.
#       [app]
#       title = My Application
#          package.name = myapp # This is all part of the title.
#
#   Buildozer's .spec files have some additional features:
#
#   Buildozer supports lists - i.e.
#       [app]
#       source.include_exts = py,png,jpg
#       #                     ^ This is a list.
#
#       [app:source.include_exts]
#       py
#       png
#       jpg
#       # ^ This is an alternative syntax for a list.
#
#   Buildozer's option names are case-sensitive, unlike most .ini files.
#
#   Buildozer supports overriding options through environment variables.
#   Name an environment variable as SECTION_OPTION to override a value in a .spec
#   file.
#
#   Buildozer support overriding options through profiles.
#   For example, you want to deploy a demo version of your application without
#   HD content. You could first change the title to add "(demo)" in the name
#   and extend the excluded directories to remove the HD content.
#
#       [app@demo]
#       title = My Application (demo)
#
#       [app:source.exclude_patterns@demo]
#       images/hd/*
#
#   Then, invoke the command line with the "demo" profile:
#
#        buildozer --profile demo android debug
#
#   Environment variable overrides have priority over profile overrides.
