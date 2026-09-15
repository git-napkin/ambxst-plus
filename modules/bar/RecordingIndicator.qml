pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.modules.services
import qs.modules.components
import qs.modules.theme
import qs.config

// Appears only while a screen recording is active. Click stops the recording.
Item {
    id: root

    property bool vertical: false
    property bool isHovered: false
    property bool enableShadow: true

    property real radius: 0
    property real startRadius: radius
    property real endRadius: radius

    visible: ScreenRecorder.isRecording
    implicitWidth: 36
    implicitHeight: 36
    Layout.preferredWidth: 36
    Layout.preferredHeight: 36

    property real pulse: 0
    SequentialAnimation on pulse {
        running: root.visible
        loops: Animation.Infinite
        NumberAnimation {
            to: 1
            duration: 800
            easing.type: Easing.InOutSine
        }
        NumberAnimation {
            to: 0
            duration: 800
            easing.type: Easing.InOutSine
        }
    }

    HoverHandler {
        onHoveredChanged: root.isHovered = hovered
    }

    StyledRect {
        id: buttonBg
        variant: "bg"
        anchors.fill: parent
        enableShadow: root.enableShadow

        topLeftRadius: root.vertical ? root.startRadius : root.startRadius
        topRightRadius: root.vertical ? root.startRadius : root.endRadius
        bottomLeftRadius: root.vertical ? root.endRadius : root.startRadius
        bottomRightRadius: root.vertical ? root.endRadius : root.endRadius

        Rectangle {
            anchors.fill: parent
            color: Styling.srItem("overprimary")
            opacity: clickArea.containsPress ? Styling.pressAlpha : (root.isHovered ? Styling.hoverAlpha : 0)
            radius: parent.radius ?? 0

            Behavior on opacity {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Config.animDuration / 2
                }
            }
        }

        Text {
            anchors.centerIn: parent
            text: Icons.stop
            font.family: Icons.font
            font.pixelSize: Styling.fontSize(0)
            color: Colors.recordingFrameColor
        }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius ?? 0
            color: "transparent"
            border.width: 2
            border.color: Colors.recordingFrameColor
            opacity: 0.3 + 0.4 * root.pulse
            scale: 1 + 0.08 * root.pulse
        }

        MouseArea {
            id: clickArea
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: ScreenRecorder.stopRecording()
        }

        StyledToolTip {
            show: root.isHovered
            tooltipText: ScreenRecorder.duration
                ? qsTr("Stop recording (%1)").arg(ScreenRecorder.duration)
                : qsTr("Stop recording")
        }
    }

    Component.onCompleted: ScreenRecorder.initialize()
}
