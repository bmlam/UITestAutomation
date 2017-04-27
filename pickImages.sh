#!/bin/bash

sourceDir=$1
targetDirBaseName=$2

baseLoc=~/Desktop/pickImages

targetDirFull=$baseLoc/$targetDirBaseName

echo "targetDirFull: $targetDirFull"
mkdir -p $targetDirFull

cd $sourceDir
cp P__ShouldBeActiveTimersView.png $targetDirFull/P1_activeTimers.png
cp P__CouldBeNotifsPermissionsAlert.png $targetDirFull/P2_presets.png
cp P__DidSaveTimerDetails.png $targetDirFull/P3_newPreset.png
cp P__SoundRecorderStoppedRecording.png $targetDirFull/P4_soundRecorder.png

