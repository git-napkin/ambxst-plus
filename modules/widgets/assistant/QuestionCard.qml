import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config

StyledRect {
    id: root
    property var call: ({})
    variant: "surface"
    radius: Styling.popupRadius() - 8
    implicitHeight: col.implicitHeight + 20
    implicitWidth: parent ? parent.width : 240

    property var answers: ({})

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        spacing: 12

        Repeater {
            model: call.items || []
            delegate: ColumnLayout {
                id: qBlock
                required property var modelData
                Layout.fillWidth: true
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: modelData.question || ""
                    wrapMode: Text.Wrap
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-1)
                    color: Colors.overSurface
                }

                Repeater {
                    model: (modelData.question_type && modelData.question_type.options) || []
                    delegate: StyledRect {
                        required property var modelData
                        Layout.fillWidth: true
                        variant: qBlock._selected(modelData.label) ? "primary" : "internalbg"
                        radius: Styling.radius(-4)
                        implicitHeight: optLabel.implicitHeight + 16

                        Text {
                            id: optLabel
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: 10
                            wrapMode: Text.Wrap
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-2)
                            color: qBlock._selected(modelData.label) ? Colors.overPrimary : Colors.overSurface
                            text: (modelData.recommended ? "★ " : "") + (modelData.label || "")
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: qBlock._toggle(modelData.label)
                        }
                    }
                }

                TextField {
                    visible: !!(modelData.question_type && modelData.question_type.supports_other)
                    Layout.fillWidth: true
                    placeholderText: qsTr("Other…")
                    font.family: Config.theme.font
                    color: Colors.overSurface
                    onTextChanged: {
                        const copy = Object.assign({}, root.answers);
                        copy[modelData.question_id || modelData.question] = text;
                        root.answers = copy;
                    }
                    background: StyledRect {
                        variant: "internalbg"
                        radius: Styling.radius(-4)
                    }
                }

                function _selected(label) {
                    const key = modelData.question_id || modelData.question;
                    const val = root.answers[key];
                    if (Array.isArray(val))
                        return val.indexOf(label) !== -1;
                    return val === label;
                }

                function _toggle(label) {
                    const key = modelData.question_id || modelData.question;
                    const multi = !!(modelData.question_type && modelData.question_type.is_multiselect);
                    const copy = Object.assign({}, root.answers);
                    if (multi) {
                        let cur = Array.isArray(copy[key]) ? copy[key].slice() : [];
                        const i = cur.indexOf(label);
                        if (i === -1)
                            cur.push(label);
                        else
                            cur.splice(i, 1);
                        copy[key] = cur;
                    } else {
                        copy[key] = label;
                    }
                    root.answers = copy;
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }

            StyledRect {
                variant: "primary"
                radius: Styling.radius(-4)
                implicitHeight: 28
                implicitWidth: sendLabel.implicitWidth + 20
                scale: sendArea.pressed ? 0.96 : 1

                Text {
                    id: sendLabel
                    anchors.centerIn: parent
                    text: qsTr("Answer")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-2)
                    color: Colors.overPrimary
                }

                MouseArea {
                    id: sendArea
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        const items = call.items || [];
                        const payload = [];
                        for (let i = 0; i < items.length; i++) {
                            const q = items[i];
                            const key = q.question_id || q.question;
                            payload.push({
                                question_id: q.question_id || "",
                                answer: root.answers[key]
                            });
                        }
                        Ai.answerQuestions(call.call_id, payload);
                    }
                }
            }
        }
    }
}
