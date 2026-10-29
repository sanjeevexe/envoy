# Envoy Android toolchain environment on the Linux VM: what scripts/env.sh does on the Mac. Source it.
#
# ANDROID_HOME is ~/Library/Android/sdk, the Mac's path, which vm-setup.sh links to ~/android-sdk: the repo's scripts
# (start_emulator.sh and stop_emulator.sh source the Mac's env.sh) and backend/devices/android.py's default then
# resolve without any change. JAVA_HOME is only for sdkmanager and avdmanager; the emulator and adb don't use it.
export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$HOME/.local/bin:$HOME/node/bin:$PATH"
# The emulator writes its gRPC token to $XDG_RUNTIME_DIR/avd/running, where backend/devices/emulator_grpc.py reads it.
# A login session sets it; this keeps the two in step for anything started without one.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
# No GPU on the VM: software rendering, through ANGLE on SwiftShader (scripts/start_emulator.sh appends these).
# Not -gpu swiftshader_indirect: on Oct 29 that renderer crashed the emulator (a segfault in its RenderThread) when
# DoorDash and Amazon drew their screens; with swangle the same Amazon run completed. And no host video decoder: an
# emulator on swangle still died while apps played video ("h264 no frame" in its log); apps then decode in Android.
export EMULATOR_EXTRA_ARGS="${EMULATOR_EXTRA_ARGS:--gpu swangle -feature -HardwareDecoder}"
