import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: appWindow
    objectName: "agentWindow"
    visible: true
    width: 840; height: 810
    minimumWidth: 700; minimumHeight: 620
    title: "Vox — Groq voice control"
    color: theme.background
    Theme { id: theme }
    NotchWindow { objectName: "notchWindow" }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            width: appWindow.width - 76
            x: 38
            spacing: 0
            Item { Layout.preferredHeight: 34 }
            RowLayout {
                Layout.fillWidth: true
                Rectangle { width: 35; height: 35; radius: 11; color: "#242136"; Text { anchors.centerIn: parent; text: "✦"; color: theme.accent; font.pixelSize: 19 } }
                Text { text: "VOX"; color: "#d4d8e4"; font.family: theme.fontFamily; font.bold: true; font.pixelSize: 11; font.letterSpacing: 1.6 }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 190; height: 28; radius: 14
                    color: viewModel.recording ? "#462b2a" : (viewModel.handsFree ? "#1d3329" : (viewModel.busy ? "#27324b" : "#211e31"))
                    border.color: viewModel.recording ? "#a5584e" : (viewModel.handsFree ? "#3d7a5c" : (viewModel.busy ? "#4e6caa" : "#3a3451"))
                    Text { anchors.centerIn: parent; text: viewModel.recording ? "●  MICROPHONE ON" : (viewModel.handsFree ? "●  LISTENING FOR 'HI VOX'" : (viewModel.busy ? "●  WORKING ONLINE" : "MICROPHONE OFF")); color: viewModel.recording ? "#ffc0b3" : (viewModel.handsFree ? "#a9e8c6" : "#c0b5f6"); font.bold: true; font.pixelSize: 9; font.letterSpacing: 0.7 }
                }
            }
            Item { Layout.preferredHeight: 30 }
            Text { text: "Your voice, your PC."; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 32; font.weight: Font.DemiBold; font.letterSpacing: -1 }
            Item { Layout.preferredHeight: 7 }
            Text { text: "Turn on Hands-free, then just say “Hi Vox” — or type a request below. Wake-word listening happens on this PC; nothing is sent online until Vox wakes."; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Item { Layout.preferredHeight: 20 }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 65; radius: 14
                color: "#1d1a20"; border.color: "#514033"
                ColumnLayout {
                    anchors.fill: parent; anchors.leftMargin: 17; anchors.rightMargin: 17; anchors.topMargin: 11; anchors.bottomMargin: 11; spacing: 3
                    Text { text: "Supported: apps, websites, folders, typing, scroll, window control, files, screenshots, clipboard"; color: "#f5d6b4"; font.family: theme.fontFamily; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Text { text: "Consequential actions ask for confirmation first; anything else is unavailable."; color: "#ad9989"; font.family: theme.fontFamily; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
            }
            Item { Layout.preferredHeight: 20 }
            Text { text: "Groq API key"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 14; font.bold: true }
            Item { Layout.preferredHeight: 7 }
            RowLayout {
                Layout.fillWidth: true; spacing: 9
                TextField {
                    id: keyInput
                    objectName: "keyInput"
                    Layout.fillWidth: true; Layout.preferredHeight: 42
                    enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree
                    echoMode: TextInput.Password; placeholderText: "Paste your Groq API key here"
                    placeholderTextColor: theme.subtle; color: theme.text; leftPadding: 13; font.pixelSize: 12
                    background: Rectangle { color: "#171c25"; radius: 10; border.color: keyInput.activeFocus ? theme.accent : theme.line }
                }
                DemoButton { objectName: "saveKeyButton"; text: "Save key"; enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree; onClicked: { viewModel.saveKey(keyInput.text); keyInput.clear() } }
                DemoButton { objectName: "removeKeyButton"; text: "Remove"; enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree; onClicked: viewModel.removeKey() }
            }
            Item { Layout.preferredHeight: 7 }
            Text { text: "Saved encrypted for this Windows account. Audio, transcript and requests are sent to Groq."; color: theme.subtle; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Item { Layout.preferredHeight: 20 }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Assistant engine"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                Text { text: viewModel.engineMode === "live" ? "LIVE" : "LEGACY"; color: theme.subtle; font.bold: true; font.pixelSize: 9; font.letterSpacing: 0.6 }
            }
            Item { Layout.preferredHeight: 9 }
            RowLayout {
                Layout.fillWidth: true; spacing: 9
                Switch {
                    id: liveEngineToggle
                    objectName: "liveEngineToggle"
                    text: checked ? "Live — streaming, context and memory" : "Legacy — single-shot planning"
                    font.pixelSize: 12
                    palette.text: theme.muted
                    checked: viewModel.engineMode === "live"
                    enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree
                    onCheckedChanged: viewModel.setEngineMode(checked ? "live" : "legacy")
                }
                Item { Layout.fillWidth: true }
                DemoButton {
                    objectName: "repeatLastButton"
                    text: "Repeat last reply"
                    visible: viewModel.engineMode === "live"
                    enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree
                    onClicked: viewModel.repeatLast()
                }
            }
            Item { Layout.preferredHeight: 6 }
            Text { text: "Live mode is opt-in. It keeps conversation context on this device, streams replies, and still asks before consequential actions."; color: theme.subtle; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Item { Layout.preferredHeight: 20 }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Hands-free"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                Text { text: "ON-DEVICE WAKE WORD"; color: theme.subtle; font.bold: true; font.pixelSize: 9; font.letterSpacing: 0.6 }
            }
            Item { Layout.preferredHeight: 9 }
            RowLayout {
                Layout.fillWidth: true; spacing: 9
                Switch {
                    id: handsFreeToggle
                    objectName: "handsFreeToggle"
                    text: checked ? "On — say “Hi Vox”" : "Off"
                    font.pixelSize: 12
                    palette.text: theme.muted
                    checked: viewModel.handsFree
                    enabled: !viewModel.busy && !viewModel.approvalPending
                    onCheckedChanged: viewModel.setHandsFree(checked, dryRun.checked, speak.checked)
                }
                DemoButton { objectName: "stopButton"; text: "Stop"; enabled: viewModel.busy || viewModel.approvalPending || viewModel.handsFree; onClicked: viewModel.cancel() }
                Item { Layout.fillWidth: true }
                CheckBox {
                    id: speak
                    objectName: "speak"
                    text: "Spoken reply"; checked: true; enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree
                    contentItem: Text { text: speak.text; color: theme.muted; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: speak.indicator.width + 7 }
                }
            }
            Item { Layout.preferredHeight: 6 }
            Text { text: "While Hands-free is on, the microphone listens locally for “Hi Vox” only. Your request audio is sent to Groq after the wake phrase. Turn it off or press Stop to close the microphone."; color: theme.subtle; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Item { Layout.preferredHeight: 18 }
            Text { text: "Or type a request"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 14; font.bold: true }
            Item { Layout.preferredHeight: 8 }
            RowLayout {
                Layout.fillWidth: true; spacing: 9
                TextField {
                    id: requestInput
                    objectName: "requestInput"
                    Layout.fillWidth: true; Layout.preferredHeight: 44
                    enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree
                    placeholderText: "Try: Open Calculator"
                    placeholderTextColor: theme.subtle; color: theme.text; font.pixelSize: 13; leftPadding: 13
                    background: Rectangle { color: "#171c25"; radius: 10; border.color: requestInput.activeFocus ? theme.accent : theme.line }
                    onAccepted: viewModel.submit(text, dryRun.checked, speak.checked)
                }
                DemoButton { objectName: "runButton"; text: "Run request"; primary: true; enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree; onClicked: viewModel.submit(requestInput.text, dryRun.checked, speak.checked) }
            }
            CheckBox {
                id: dryRun
                objectName: "dryRun"
                text: "Dry run (do not perform the action)"; checked: false; enabled: !viewModel.busy && !viewModel.approvalPending && !viewModel.handsFree
                contentItem: Text { text: dryRun.text; color: theme.muted; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: dryRun.indicator.width + 7 }
            }
            Rectangle {
                visible: viewModel.approvalPending
                Layout.fillWidth: true; Layout.preferredHeight: approvalLayout.implicitHeight + 24
                radius: 12; color: "#252018"; border.color: "#a07135"
                ColumnLayout {
                    id: approvalLayout
                    anchors.fill: parent; anchors.margins: 12; spacing: 8
                    Text { text: "CONFIRM ACTION"; color: "#ffc778"; font.bold: true; font.pixelSize: 10; Layout.fillWidth: true }
                    Text { text: viewModel.approvalText; textFormat: Text.PlainText; color: theme.text; font.pixelSize: 12; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                    Text { visible: viewModel.needsWindow; text: "Place the text cursor in the target app, return here, then refresh and select its window. Text may be entered into its focused control."; textFormat: Text.PlainText; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    RowLayout {
                        visible: viewModel.needsWindow
                        Layout.fillWidth: true
                        ComboBox {
                            id: targetWindow
                            objectName: "targetWindow"
                            Layout.fillWidth: true
                            model: viewModel.windowChoices
                            currentIndex: -1
                            displayText: currentIndex < 0 ? "Choose a window…" : currentText
                            onCurrentIndexChanged: viewModel.selectWindow(currentIndex)
                            contentItem: Text { text: targetWindow.displayText; textFormat: Text.PlainText; color: theme.text; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 9 }
                            background: Rectangle { radius: 9; color: "#171c25"; border.color: theme.line }
                            delegate: ItemDelegate {
                                required property string modelData
                                width: targetWindow.width
                                contentItem: Text { text: parent.modelData; textFormat: Text.PlainText; color: theme.text; elide: Text.ElideRight }
                            }
                        }
                        DemoButton { objectName: "refreshWindowsButton"; text: "Refresh"; onClicked: { viewModel.refreshWindows(); targetWindow.currentIndex = -1 } }
                    }
                    RowLayout {
                        Item { Layout.fillWidth: true }
                        DemoButton { objectName: "declineButton"; text: "Decline"; onClicked: viewModel.deny() }
                        DemoButton { objectName: "approveButton"; text: "Confirm action"; primary: true; onClicked: viewModel.approve() }
                    }
                }
            }
            Item { Layout.preferredHeight: 12 }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: statusLayout.implicitHeight + 26; radius: 12; color: theme.surface; border.color: theme.line
                ColumnLayout {
                    id: statusLayout
                    anchors.fill: parent; anchors.margins: 13; spacing: 6
                    Text { text: "STATUS"; color: theme.subtle; font.bold: true; font.pixelSize: 9; font.letterSpacing: 1 }
                    Text { objectName: "statusText"; text: viewModel.status; color: "#c2cad7"; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Text { visible: viewModel.transcript.length > 0; text: "Heard: " + viewModel.transcript; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Text {
                        objectName: "understoodText"
                        visible: viewModel.engineMode === "live" && viewModel.lastStandalone.length > 0
                        text: "Understood: " + viewModel.lastStandalone
                        textFormat: Text.PlainText
                        color: theme.muted
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                    Text {
                        visible: viewModel.engineMode === "live" && viewModel.liveHistory.length > 0
                        text: "LIVE HISTORY"
                        color: theme.subtle
                        font.bold: true
                        font.pixelSize: 9
                        font.letterSpacing: 1
                        Layout.fillWidth: true
                    }
                    Repeater {
                        id: liveHistoryList
                        objectName: "liveHistoryList"
                        model: viewModel.engineMode === "live" ? viewModel.liveHistory : []
                        delegate: Text {
                            required property string modelData
                            text: modelData
                            textFormat: Text.PlainText
                            color: theme.muted
                            font.pixelSize: 10
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                        }
                    }
                    RowLayout {
                        visible: viewModel.handsFree
                        Layout.fillWidth: true; spacing: 8
                        Text { text: "MIC"; color: theme.subtle; font.bold: true; font.pixelSize: 9; font.letterSpacing: 1 }
                        Rectangle {
                            Layout.fillWidth: true; height: 6; radius: 3; color: "#232838"
                            Rectangle { width: parent.width * Math.min(1, viewModel.micLevel * 3); height: parent.height; radius: 3; color: "#50dfaa" }
                        }
                    }
                    Text { objectName: "wakeHeardText"; visible: viewModel.handsFree; text: viewModel.wakeHeard.length > 0 ? "Heard locally (wake word): “" + viewModel.wakeHeard + "”" : "Heard locally (wake word): — say “Hi Vox”"; textFormat: Text.PlainText; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
            }
            Item { Layout.preferredHeight: 20 }
            Text { text: "ONLINE GROQ VOICE  ·  ON-DEVICE WAKE WORD  ·  NO SCREEN CAPTURE"; color: theme.subtle; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.6; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Item { Layout.preferredHeight: 28 }
        }
    }
}
