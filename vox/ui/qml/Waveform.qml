import QtQuick

Item {
    id: root
    property color accent: "#4da3ff"
    property bool running: false
    property bool reduceMotion: false
    property real phase: 0
    implicitHeight: 27
    NumberAnimation on phase {
        from: 0; to: 6.283; duration: 1800; loops: Animation.Infinite
        running: root.running && !root.reduceMotion
    }
    Row {
        anchors.centerIn: parent
        spacing: 3
        Repeater {
            model: 36
            Rectangle {
                required property int index
                width: 3
                height: 4 + (0.3 + 0.7 * Math.abs(Math.sin(index * 0.81 + root.phase))) *
                        (5 + 15 * Math.sin(Math.PI * index / 35))
                radius: 2
                color: root.accent
                opacity: 0.35 + 0.65 * Math.sin(Math.PI * index / 35)
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
