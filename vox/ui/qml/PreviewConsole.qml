import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: studioWindow
    objectName: "previewConsole"
    visible: true
    width: 830; height: 810
    minimumWidth: 740; minimumHeight: 780
    title: "Notch design studio"
    color: theme.background
    Theme { id: theme }
    NotchWindow { objectName: "notchWindow" }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 38
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Rectangle {
                    width: 35; height: 35; radius: 11; color: "#242136"
                    Text { anchors.centerIn: parent; text: "✦"; color: theme.accent; font.pixelSize: 19 }
                }
                Text {
                    text: "NOTCH STUDIO"; color: "#d4d8e4"
                    font.family: theme.fontFamily; font.bold: true; font.pixelSize: 11; font.letterSpacing: 1.6
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 128; height: 28; radius: 14; color: "#211e31"; border.color: "#3a3451"
                    Text { anchors.centerIn: parent; text: "DESIGN PREVIEW"; color: "#c0b5f6"; font.bold: true; font.pixelSize: 9; font.letterSpacing: 0.8 }
                }
            }
            Item { Layout.preferredHeight: 40 }
            Text { text: "A quieter way to work."; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 34; font.weight: Font.DemiBold; font.letterSpacing: -1 }
            Item { Layout.preferredHeight: 9 }
            Text { text: "Explore the states of your voice-first companion."; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 14 }
            Item { Layout.preferredHeight: 30 }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 68; radius: 14
                color: "#1d1a20"; border.color: "#514033"
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18; spacing: 14
                    Rectangle {
                        width: 32; height: 32; radius: 10; color: "#3b2b1b"
                        Text { anchors.centerIn: parent; text: "!"; color: "#ffb554"; font.pixelSize: 17; font.bold: true }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        Text { text: "Sandbox simulation only"; color: "#f5d6b4"; font.family: theme.fontFamily; font.pixelSize: 12; font.bold: true }
                        Text { text: "No microphone, real PC controls or production approvals are connected."; color: "#ad9989"; font.family: theme.fontFamily; font.pixelSize: 11 }
                    }
                }
            }
            Item { Layout.preferredHeight: 28 }
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 3
                    Text { text: "Choose a moment"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 15; font.bold: true }
                    Text { text: "The notch above changes as you explore."; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 11 }
                }
                Item { Layout.fillWidth: true }
                Switch {
                    id: motionSwitch
                    text: "Reduce motion"
                    checked: viewModel.reduceMotion
                    onToggled: viewModel.setReduceMotion(checked)
                    indicator: Rectangle {
                        implicitWidth: 36; implicitHeight: 20; radius: 10
                        color: motionSwitch.checked ? theme.accent : "#303744"
                        border.color: motionSwitch.checked ? theme.accent : "#48505e"
                        Rectangle {
                            x: motionSwitch.checked ? 18 : 2; y: 2; width: 16; height: 16; radius: 8
                            color: "#f7f6fb"
                            Behavior on x { NumberAnimation { duration: 150 } }
                        }
                    }
                    contentItem: Text { text: motionSwitch.text; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: motionSwitch.indicator.width + 8 }
                }
            }
            Item { Layout.preferredHeight: 16 }
            GridLayout {
                columns: 5; rowSpacing: 8; columnSpacing: 8; Layout.fillWidth: true
                Repeater {
                    model: [
                        { key: "idle", label: "Idle", icon: "01" }, { key: "wake", label: "Wake", icon: "02" },
                        { key: "listening", label: "Listening", icon: "03" }, { key: "thinking", label: "Thinking", icon: "04" },
                        { key: "acting", label: "Acting", icon: "05" }, { key: "approval", label: "Approval", icon: "06" },
                        { key: "speaking", label: "Speaking", icon: "07" }, { key: "error", label: "Error", icon: "08" },
                        { key: "echo", label: "Quick action", icon: "09" }, { key: "panel", label: "Panel", icon: "10" }
                    ]
                    Button {
                        id: stateButton
                        required property var modelData
                        Layout.fillWidth: true; Layout.preferredHeight: 64
                        hoverEnabled: true
                        enabled: !viewModel.busy
                        leftPadding: 12; rightPadding: 10; topPadding: 9; bottomPadding: 9
                        onClicked: viewModel.selectState(modelData.key)
                        background: Rectangle {
                            radius: 11
                            color: viewModel.state === stateButton.modelData.key ? "#29243c" : (stateButton.hovered ? "#202632" : theme.surface)
                            border.color: viewModel.state === stateButton.modelData.key ? "#776baf" : theme.line
                        }
                        contentItem: Column {
                            spacing: 6
                            Text { text: stateButton.modelData.icon; color: viewModel.state === stateButton.modelData.key ? "#bfb0ff" : theme.subtle; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.8 }
                            Text { text: stateButton.modelData.label; color: viewModel.state === stateButton.modelData.key ? "#f4efff" : "#bec6d3"; font.family: theme.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold }
                        }
                    }
                }
            }
            Item { Layout.preferredHeight: 22 }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 160; radius: 14
                color: theme.surface; border.color: theme.line
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 16; spacing: 9
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "CONNECTED SANDBOX"; color: "#c0b5f6"; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1 }
                        Item { Layout.fillWidth: true }
                        Text { text: "NO REAL PC ACTIONS"; color: theme.subtle; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.7 }
                    }
                    Text { text: viewModel.demoStatus; color: "#c2cad7"; font.family: theme.fontFamily; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 7
                        DemoButton { objectName: "demoOpen"; text: "Simulate opening Notepad"; Layout.fillWidth: true; enabled: !viewModel.busy; onClicked: viewModel.startDemo("open") }
                        DemoButton { objectName: "demoDelete"; text: "Simulate deleting files"; Layout.fillWidth: true; enabled: !viewModel.busy; onClicked: viewModel.startDemo("delete") }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 7
                        DemoButton { objectName: "demoDeny"; text: "Deny"; Layout.fillWidth: true; enabled: viewModel.approvalPending; onClicked: viewModel.resolveDemo(false) }
                        DemoButton { objectName: "demoApprove"; text: "Approve simulation"; primary: true; Layout.fillWidth: true; enabled: viewModel.approvalPending; onClicked: viewModel.resolveDemo(true) }
                        DemoButton { objectName: "demoStop"; text: "Stop"; Layout.fillWidth: true; enabled: viewModel.busy && !viewModel.stopping; onClicked: viewModel.stopDemo() }
                    }
                }
            }
            Item { Layout.fillHeight: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
            Item { Layout.preferredHeight: 17 }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "NATIVE UI  /  EARLY CONCEPT"; color: theme.subtle; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.1 }
                Item { Layout.fillWidth: true }
                Text { text: "Select a state to preview  ↑"; color: theme.muted; font.pixelSize: 11 }
            }
        }
    }
}
