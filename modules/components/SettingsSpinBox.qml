pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme
import qs.modules.components

StyledRect {
    id: root

    property int value: 0
    property int from: 0
    property int to: 100
    property int stepSize: 1
    property string suffix: ""

    signal valueEdited(int newValue)

    variant: "common"
    implicitHeight: 36
    implicitWidth: 132
    Layout.preferredHeight: implicitHeight
    Layout.preferredWidth: implicitWidth
    Layout.alignment: Qt.AlignVCenter
    radius: Styling.radius(-2)
    opacity: enabled ? 1 : 0.4

    function clamp(val) {
        return Math.max(root.from, Math.min(root.to, val));
    }

    function commit(val) {
        const next = root.clamp(val);
        if (next !== root.value)
            root.valueEdited(next);
        input.text = next.toString();
    }

    function nudge(direction) {
        root.commit(root.value + direction * root.stepSize);
    }

    function startRepeat(direction) {
        root.nudge(direction);
        holdDelay.direction = direction;
        holdDelay.restart();
    }

    function stopRepeat() {
        holdDelay.stop();
        repeatTimer.stop();
    }

    Timer {
        id: holdDelay
        interval: 400
        repeat: false
        property int direction: 1
        onTriggered: {
            repeatTimer.direction = direction;
            repeatTimer.start();
        }
    }

    Timer {
        id: repeatTimer
        interval: 80
        repeat: true
        property int direction: 1
        onTriggered: root.nudge(direction)
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 3
        spacing: 0

        Item {
            implicitWidth: 28
            implicitHeight: 28
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            opacity: root.enabled && root.value > root.from ? 1 : 0.35

            StyledRect {
                anchors.fill: parent
                variant: minusMouse.containsMouse && root.enabled ? "focus" : "transparent"
                radius: Math.max(0, root.radius - 3)
                Text {
                    anchors.centerIn: parent
                    text: Icons.minus
                    font.family: Icons.font
                    font.pixelSize: Styling.fontSize(-1)
                    color: Colors.overBackground
                }
            }

            MouseArea {
                id: minusMouse
                anchors.fill: parent
                enabled: root.enabled && root.value > root.from
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPressed: root.startRepeat(-1)
                onReleased: root.stopRepeat()
                onCanceled: root.stopRepeat()
            }
        }

        TextInput {
            id: input
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: root.value.toString()
            font.family: Config.theme.monoFont
            font.pixelSize: Styling.monoFontSize(0)
            color: Colors.overBackground
            horizontalAlignment: TextInput.AlignHCenter
            verticalAlignment: TextInput.AlignVCenter
            selectByMouse: true
            clip: true
            enabled: root.enabled
            validator: IntValidator {
                bottom: root.from
                top: root.to
            }

            readonly property int configValue: root.value
            onConfigValueChanged: {
                if (!activeFocus && text !== configValue.toString())
                    text = configValue.toString();
            }

            onEditingFinished: {
                const parsed = parseInt(text);
                if (isNaN(parsed))
                    text = root.value.toString();
                else
                    root.commit(parsed);
            }
        }

        Text {
            visible: root.suffix !== ""
            text: root.suffix
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-2)
            color: Colors.overSurfaceVariant
            Layout.rightMargin: 4
        }

        Item {
            implicitWidth: 28
            implicitHeight: 28
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            opacity: root.enabled && root.value < root.to ? 1 : 0.35

            StyledRect {
                anchors.fill: parent
                variant: plusMouse.containsMouse && root.enabled ? "focus" : "transparent"
                radius: Math.max(0, root.radius - 3)
                Text {
                    anchors.centerIn: parent
                    text: Icons.plus
                    font.family: Icons.font
                    font.pixelSize: Styling.fontSize(-1)
                    color: Colors.overBackground
                }
            }

            MouseArea {
                id: plusMouse
                anchors.fill: parent
                enabled: root.enabled && root.value < root.to
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPressed: root.startRepeat(1)
                onReleased: root.stopRepeat()
                onCanceled: root.stopRepeat()
            }
        }
    }
}
