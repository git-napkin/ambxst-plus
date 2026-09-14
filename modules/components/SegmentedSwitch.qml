pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme
import qs.modules.components

// Multi-option selector. `model` is strings or { value/id, label } objects.
Item {
    id: root

    property var model: []
    property var currentValue
    property int implicitRowHeight: 36

    signal activated(var value)

    implicitHeight: implicitRowHeight
    implicitWidth: 240
    Layout.fillWidth: true
    Layout.preferredHeight: implicitRowHeight

    function optionValue(item) {
        if (item && typeof item === "object")
            return item.value !== undefined ? item.value : item.id;
        return item;
    }

    function optionLabel(item) {
        if (item && typeof item === "object")
            return item.label !== undefined ? item.label : String(root.optionValue(item));
        return String(item);
    }

    function optionIndex(value) {
        const items = root.model || [];
        for (let i = 0; i < items.length; i++) {
            if (root.optionValue(items[i]) === value)
                return i;
        }
        return 0;
    }

    readonly property int count: (root.model || []).length
    readonly property int currentIndex: optionIndex(currentValue)
    readonly property int pad: 3
    readonly property real segmentWidth: count > 0 ? (width - pad * 2) / count : 0

    StyledRect {
        id: track
        anchors.fill: parent
        variant: "internalbg"
        radius: Styling.radius(-2)

        StyledRect {
            id: highlight
            variant: "primary"
            x: root.pad + root.currentIndex * root.segmentWidth
            y: root.pad
            width: Math.max(0, root.segmentWidth)
            height: Math.max(0, parent.height - root.pad * 2)
            radius: Math.max(0, track.radius - root.pad)
            visible: root.count > 0

            Behavior on x {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingInOut
                }
            }
        }

        Row {
            id: row
            anchors.fill: parent
            anchors.margins: root.pad
            spacing: 0
            z: 1

            Repeater {
                model: root.model

                delegate: Item {
                    id: seg
                    required property var modelData
                    required property int index

                    readonly property bool selected: root.optionValue(modelData) === root.currentValue
                    readonly property bool hovered: segMouse.containsMouse

                    width: root.segmentWidth
                    height: row.height

                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 6
                        text: root.optionLabel(seg.modelData)
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-1)
                        font.weight: seg.selected ? Font.DemiBold : Font.Normal
                        color: seg.selected ? highlight.item : Colors.overBackground
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight

                        Behavior on color {
                            enabled: Config.animDuration > 0
                            ColorAnimation {
                                duration: Styling.animQuick
                            }
                        }
                    }

                    MouseArea {
                        id: segMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.activated(root.optionValue(seg.modelData))
                    }
                }
            }
        }
    }
}
