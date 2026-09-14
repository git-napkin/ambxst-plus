pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme

// Ambxst[+]-native on/off control. Controlled: bind `checked`, handle `toggled`.
Item {
    id: root

    property bool checked: false

    signal toggled(bool checked)

    readonly property int trackWidth: 44
    readonly property int trackHeight: 24
    readonly property int thumbSize: 18

    implicitWidth: 52
    implicitHeight: 36
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
    Keys.onReturnPressed: event => {
        root.toggle();
        event.accepted = true;
    }

    Rectangle {
        id: track
        anchors.centerIn: parent
        width: root.trackWidth
        height: root.trackHeight
        radius: height / 2
        color: root.checked ? Styling.srItem("overprimary") : Colors.surfaceBright
        border.width: root.checked ? 0 : 1
        border.color: root.activeFocus ? Styling.srItem("overprimary") : Colors.outline
        scale: mouseArea.pressed ? 0.96 : 1

        Behavior on color {
            enabled: Config.animDuration > 0
            ColorAnimation {
                duration: Styling.animQuick
                easing.type: Styling.animEasingInOut
            }
        }
        Behavior on scale {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Styling.animInstant
                easing.type: Styling.animEasingOut
            }
        }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: Colors.overBackground
            opacity: mouseArea.containsMouse && root.enabled ? Styling.hoverAlpha : 0
            Behavior on opacity {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animInstant
                }
            }
        }

        Rectangle {
            id: thumb
            width: root.thumbSize
            height: root.thumbSize
            radius: width / 2
            y: (track.height - height) / 2
            x: root.checked ? track.width - width - 3 : 3
            color: root.checked ? Colors.background : Colors.overSurfaceVariant

            Behavior on x {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingInOut
                }
            }
            Behavior on color {
                enabled: Config.animDuration > 0
                ColorAnimation {
                    duration: Styling.animQuick
                }
            }
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggle()
    }
}
