import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    implicitHeight: 34
    leftPadding: 12; rightPadding: 12
    background: Rectangle {
        radius: 9
        color: !control.enabled ? "#171c24" : (control.primary ? "#b8aaff" : (control.hovered ? "#303847" : "#242a35"))
        border.color: control.activeFocus ? "#e6ddff" : "transparent"
    }
    contentItem: Text {
        text: control.text
        color: !control.enabled ? "#576170" : (control.primary ? "#1b1728" : "#dbe1ea")
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        font.family: "Segoe UI"; font.pixelSize: 11; font.bold: true
        elide: Text.ElideRight
    }
}
