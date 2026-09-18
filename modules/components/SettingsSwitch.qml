pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme
import qs.modules.components

// Ambxst[+]-native on/off control. Controlled: bind `checked`, handle `toggled`.
// Track and thumb are StyledRects so they share shell radius and variant
// surfaces (including half-tone) with buttons, checkboxes, and chips —
// not a Material/iOS pill.
Item {
    id: root

    property bool checked: false

    signal toggled(bool checked)

    // Match PanelTitlebar action buttons (28px, radius(-4)) so the thumb
    // stays a rounded square at default roundness instead of collapsing
    // into a circle. Track is taller than a pill's 2*radius capsule.
    readonly property int trackWidth: 52
    readonly property int trackHeight: 32
    readonly property int thumbSize: 28
    readonly property int thumbPad: 2

    implicitWidth: 60
    implicitHeight: 36
    Layout.preferredWidth: implicitWidth
    Layout.preferredHeight: implicitHeight
    Layout.alignment: Qt.AlignVCenter
    activeFocusOnTab: enabled
    Accessible.role: Accessible.CheckBox
    Accessible.checkable: true
    Accessible.checked: checked
    Accessible.onPressAction: root.toggle()
    opacity: enabled ? 1 : 0.4

    readonly property string trackVariant: root.checked ? "primary" : (mouseArea.containsMouse ? "focus" : "internalbg")
    readonly property string thumbVariant: root.checked ? "overprimary" : "common"

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

    StyledRect {
        id: track
        anchors.centerIn: parent
        width: root.trackWidth
        height: root.trackHeight
        variant: root.trackVariant
        radius: Styling.radius(-4)
        scale: mouseArea.pressed ? 0.96 : 1

        Behavior on scale {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Styling.animInstant
                easing.type: Styling.animEasingOut
            }
        }

        StyledRect {
            id: thumb
            width: root.thumbSize
            height: root.thumbSize
            variant: root.thumbVariant
            radius: Styling.radius(-4)
            y: (track.height - height) / 2
            x: root.checked ? track.width - width - root.thumbPad : root.thumbPad

            Behavior on x {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingInOut
                }
            }
        }
    }

    Rectangle {
        anchors.fill: track
        radius: track.radius
        color: "transparent"
        border.width: root.activeFocus ? 1 : 0
        border.color: Styling.srItem("overprimary")
        opacity: 0.7
        visible: root.activeFocus
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
