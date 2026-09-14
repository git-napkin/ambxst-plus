pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme
import qs.modules.components

StyledRect {
    id: root

    property string text: ""
    property string icon: ""
    property string kind: "primary"

    signal clicked

    readonly property bool hovered: mouse.containsMouse
    readonly property bool pressed: mouse.pressed
    readonly property string visualKind: {
        if (!enabled)
            return kind;
        if (pressed) {
            if (kind === "primary")
                return "overprimary";
            if (kind === "error")
                return "overerror";
            return "focus";
        }
        if (hovered) {
            if (kind === "primary")
                return "primaryfocus";
            if (kind === "error")
                return "errorfocus";
            return "focus";
        }
        return kind;
    }

    variant: visualKind
    implicitHeight: 36
    implicitWidth: Math.max(72, row.implicitWidth + 20)
    Layout.preferredHeight: implicitHeight
    Layout.preferredWidth: implicitWidth
    Layout.alignment: Qt.AlignVCenter
    radius: Styling.radius(-2)
    opacity: enabled ? 1 : 0.4
    scale: pressed && enabled ? 0.96 : 1

    Behavior on scale {
        enabled: Config.animDuration > 0
        NumberAnimation {
            duration: Styling.animInstant
            easing.type: Styling.animEasingOut
        }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 6

        Text {
            visible: root.icon !== ""
            text: root.icon
            font.family: Icons.font
            font.pixelSize: Styling.fontSize(0)
            color: root.item
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            visible: root.text !== ""
            text: root.text
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-1)
            font.weight: Font.DemiBold
            color: root.item
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
