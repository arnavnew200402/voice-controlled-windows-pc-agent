import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property color edgeColor: "#8994a6"
    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeWidth: 1
            strokeColor: Qt.rgba(root.edgeColor.r, root.edgeColor.g, root.edgeColor.b, 0.55)
            fillColor: "#090b0f"
            startX: 0; startY: 0
            PathLine { x: root.width; y: 0 }
            PathQuad { x: root.width - 10; y: 10; controlX: root.width - 10; controlY: 0 }
            PathLine { x: root.width - 10; y: root.height - 24 }
            PathQuad { x: root.width - 34; y: root.height; controlX: root.width - 10; controlY: root.height }
            PathLine { x: 34; y: root.height }
            PathQuad { x: 10; y: root.height - 24; controlX: 10; controlY: root.height }
            PathLine { x: 10; y: 10 }
            PathQuad { x: 0; y: 0; controlX: 10; controlY: 0 }
        }
    }
}
