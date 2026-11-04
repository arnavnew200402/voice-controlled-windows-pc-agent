import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: appWindow
    objectName: "agentWindow"
    visible: true
    width: 790; height: 680
    minimumWidth: 700; minimumHeight: 620
    title: "Vox — early Windows preview"
    color: theme.background
    Theme { id: theme }
    NotchWindow { objectName: "notchWindow" }

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
            Text { text: "VOX"; color: "#d4d8e4"; font.family: theme.fontFamily; font.bold: true; font.pixelSize: 11; font.letterSpacing: 1.6 }
            Item { Layout.fillWidth: true }
            Rectangle {
                width: 148; height: 28; radius: 14
                color: viewModel.busy ? "#27324b" : "#211e31"; border.color: viewModel.busy ? "#4e6caa" : "#3a3451"
                Text { anchors.centerIn: parent; text: viewModel.busy ? "●  CLOUD ACTIVE" : "EARLY PREVIEW"; color: viewModel.busy ? "#a9c7ff" : "#c0b5f6"; font.bold: true; font.pixelSize: 9; font.letterSpacing: 0.8 }
            }
        }
        Item { Layout.preferredHeight: 44 }
        Text { text: "A quieter way to work."; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 34; font.weight: Font.DemiBold; font.letterSpacing: -1 }
        Item { Layout.preferredHeight: 9 }
        Text { text: "Start with a simple text request to your PC."; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 14 }
        Item { Layout.preferredHeight: 28 }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 78; radius: 14
            color: "#1d1a20"; border.color: "#514033"
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18; spacing: 14
                Rectangle { width: 32; height: 32; radius: 10; color: "#3b2b1b"; Text { anchors.centerIn: parent; text: "!"; color: "#ffb554"; font.pixelSize: 17; font.bold: true } }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 3
                    Text { text: "Limited preview — Notepad only"; color: "#f5d6b4"; font.family: theme.fontFamily; font.pixelSize: 12; font.bold: true }
                    Text { text: "Voice, general PC control and offline mode are not available yet."; color: "#ad9989"; font.family: theme.fontFamily; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
            }
        }
        Item { Layout.preferredHeight: 26 }
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true; spacing: 3
                Text { text: "ChatGPT connection"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 15; font.bold: true }
                Text { text: "Sign in through your browser. Your request is sent online."; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 11 }
            }
            DemoButton { objectName: "loginButton"; text: "Continue with ChatGPT"; enabled: !viewModel.busy; onClicked: viewModel.login() }
        }
        Item { Layout.preferredHeight: 26 }
        Text { text: "Your request"; color: theme.text; font.family: theme.fontFamily; font.pixelSize: 15; font.bold: true }
        Item { Layout.preferredHeight: 10 }
        TextField {
            id: requestInput
            objectName: "requestInput"
            Layout.fillWidth: true; Layout.preferredHeight: 48
            enabled: !viewModel.busy
            placeholderText: "Try: Open Notepad"
            placeholderTextColor: theme.subtle; color: theme.text
            font.family: theme.fontFamily; font.pixelSize: 13
            leftPadding: 14; rightPadding: 14
            background: Rectangle { color: "#171c25"; radius: 11; border.color: requestInput.activeFocus ? "#a394ff" : theme.line }
            onAccepted: viewModel.submit(text, dryRun.checked)
        }
        Item { Layout.preferredHeight: 12 }
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            CheckBox {
                id: dryRun
                objectName: "dryRun"
                text: "Dry run (no app opens)"; checked: true; enabled: !viewModel.busy
                contentItem: Text { text: dryRun.text; color: theme.muted; font.family: theme.fontFamily; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: dryRun.indicator.width + 8 }
            }
            Item { Layout.fillWidth: true }
            DemoButton { objectName: "stopButton"; text: "Stop"; enabled: viewModel.busy; onClicked: viewModel.cancel() }
            DemoButton { objectName: "runButton"; text: "Run request"; primary: true; enabled: !viewModel.busy; onClicked: viewModel.submit(requestInput.text, dryRun.checked) }
        }
        Item { Layout.preferredHeight: 22 }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 70; radius: 12; color: theme.surface; border.color: theme.line
            ColumnLayout {
                anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; anchors.topMargin: 11; anchors.bottomMargin: 11
                Text { text: "STATUS"; color: theme.subtle; font.bold: true; font.pixelSize: 9; font.letterSpacing: 1 }
                Text { text: viewModel.status; color: "#c2cad7"; font.family: theme.fontFamily; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
            }
        }
        Item { Layout.fillHeight: true }
        Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
        Item { Layout.preferredHeight: 16 }
        Text { text: "NO AUDIO OR SCREEN CAPTURE  ·  ONLINE TEXT ONLY"; color: theme.subtle; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.8 }
    }
}
