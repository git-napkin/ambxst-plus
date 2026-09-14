pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme
import qs.modules.components

Item {
    id: root

    property bool checked: false

    signal toggled(bool checked)

    implicitWidth: 40
    implicitHeight: 40
    Layout.preferredWidth: implicitWidth
    Layout.preferredHeight: implicitHeight
    Layout.alignment: Qt.AlignVCenter
    activeFocusOnTab: enabled
    Accessible.role: Accessible.CheckBox
    Accessible.checkable: true
    Accessible.checked: checked
    Accessible.onPressAction: root.toggle()

    function toggle() {
        if (!enabled)
            return;
        root.toggled(!root.checked);
    }

    Keys.onSpacePressed: event => {
        root.toggle();
        event.accepted = true;
    }

    StyledRect {
        id: box
        anchors.centerIn: parent
        width: 22
        height: 22
        variant: root.checked ? "primary" : (mouse.containsMouse ? "focus" : "common")
        radius: Styling.radius(-4)
        scale: mouse.pressed ? 0.96 : 1

        Behavior on scale {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Styling.animInstant
                easing.type: Styling.animEasingOut
            }
        }

        Text {
            anchors.centerIn: parent
            text: Icons.accept
            font.family: Icons.font
            font.pixelSize: Styling.fontSize(-1)
            color: box.item
            opacity: root.checked ? 1 : 0
            scale: root.checked ? 1 : 0.25

            Behavior on opacity {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingOut
                }
            }
            Behavior on scale {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingOut
                }
            }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggle()
    }
}
