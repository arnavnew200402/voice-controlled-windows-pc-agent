import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: win
    width: 560
    height: 260
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput
    title: "Notch preview — simulated"
    visible: true
    Theme { id: theme }

    Item {
        id: notch
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        width: viewModel.notchWidth
        height: viewModel.notchHeight
        Behavior on width { NumberAnimation { duration: viewModel.reduceMotion ? 150 : 300; easing.type: Easing.OutCubic } }
        Behavior on height { NumberAnimation { duration: viewModel.reduceMotion ? 150 : 300; easing.type: Easing.OutCubic } }

        NotchShape { anchors.fill: parent; edgeColor: viewModel.accent }
        Rectangle {
            x: 35; y: 1; width: parent.width - 70; height: 1
            color: viewModel.accent; opacity: 0.45
        }
        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 32; anchors.rightMargin: 32
            anchors.topMargin: viewModel.kind === "idle" ? 8 : 17
            anchors.bottomMargin: 17
            spacing: 7
            RowLayout {
                Layout.fillWidth: true
                spacing: 9
                Rectangle { width: 7; height: 7; radius: 4; color: viewModel.accent }
                Text {
                    Layout.fillWidth: true
                    color: viewModel.accent; text: viewModel.eyebrow
                    font.family: theme.fontFamily; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.15
                    elide: Text.ElideRight
                }
                Text {
                    text: viewModel.previewLabel; color: theme.subtle
                    font.family: theme.fontFamily; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1
                }
            }
            Text {
                visible: viewModel.kind !== "idle"
                Layout.fillWidth: true
                text: viewModel.title; color: theme.text
                font.family: theme.fontFamily; font.pixelSize: viewModel.kind === "approval" ? 16 : 18
                font.weight: Font.DemiBold; elide: Text.ElideRight
            }
            Text {
                visible: viewModel.kind !== "idle" && viewModel.kind !== "echo"
                Layout.fillWidth: true
                text: viewModel.detail; color: theme.muted
                font.family: theme.fontFamily; font.pixelSize: 12
                elide: Text.ElideRight
            }
            Waveform {
                visible: viewModel.kind === "wave" || viewModel.kind === "reply"
                running: visible
                reduceMotion: viewModel.reduceMotion
                accent: viewModel.accent
                Layout.fillWidth: true; Layout.preferredHeight: 27
            }
            RowLayout {
                visible: viewModel.kind === "action"
                Layout.fillWidth: true
                spacing: 5
                Repeater {
                    model: 2
                    Rectangle {
                        required property int index
                        Layout.fillWidth: true; height: 3; radius: 2
                        color: index === 0 ? viewModel.accent : "#27313a"
                    }
                }
            }
            RowLayout {
                visible: viewModel.kind === "echo"
                Layout.fillWidth: true; spacing: 10
                Rectangle {
                    Layout.fillWidth: true; height: 4; radius: 2; color: "#2a313b"
                    Rectangle { width: parent.width * 0.3; height: parent.height; radius: 2; color: viewModel.accent }
                }
                Text { text: viewModel.detail; color: theme.text; font.pixelSize: 12; font.bold: true }
            }
            RowLayout {
                visible: viewModel.kind === "approval"
                Layout.fillWidth: true; spacing: 8
                Rectangle {
                    Layout.fillWidth: true; height: 34; radius: 10; color: "#262329"
                    Text { anchors.centerIn: parent; text: "Not now"; color: "#ddd8d2"; font.pixelSize: 12; font.bold: true }
                }
                Rectangle {
                    Layout.fillWidth: true; height: 34; radius: 10; color: "#ffae36"
                    Text { anchors.centerIn: parent; text: "Confirm"; color: "#261a0c"; font.pixelSize: 12; font.bold: true }
                }
            }
            Text {
                visible: viewModel.kind === "approval"
                text: viewModel.busy ? "Sandbox only · use studio controls" : "Preview only · buttons are inactive"; color: theme.subtle
                font.family: theme.fontFamily; font.pixelSize: 10
            }
            Rectangle {
                visible: viewModel.kind === "panel"
                Layout.fillWidth: true; Layout.preferredHeight: 43
                radius: 11; color: "#191d25"; border.color: "#292f39"
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 13; anchors.rightMargin: 13
                    Text { text: "Ask anything…"; color: theme.subtle; font.pixelSize: 12; Layout.fillWidth: true }
                    Text { text: "PREVIEW"; color: theme.subtle; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.8 }
                }
            }
            RowLayout {
                visible: viewModel.kind === "panel"
                Layout.fillWidth: true; spacing: 8
                Repeater {
                    model: ["Mode  ·  Auto", "Mic  ·  Preview", "Settings"]
                    Rectangle {
                        required property string modelData
                        Layout.fillWidth: true; height: 32; radius: 9; color: "#191d25"
                        Text { anchors.centerIn: parent; text: parent.modelData; color: "#aab3c2"; font.pixelSize: 10 }
                    }
                }
            }
            Item { Layout.fillHeight: true }
        }
    }
}
