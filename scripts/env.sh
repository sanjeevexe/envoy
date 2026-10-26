# Envoy Android toolchain environment. Source it: `source scripts/env.sh`
# (or add `source ~/Desktop/Envoy/scripts/env.sh` to ~/.zshrc).
#
# arm64 JDK 21 from Homebrew. The Temurin 21 in /Library/Java is x86_64 and runs under Rosetta.
export JAVA_HOME="/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$HOME/.local/bin:$PATH"
