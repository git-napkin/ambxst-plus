import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config

StyledRect {
    id: root
    variant: "popup"
    radius: Styling.popupRadius()

    property string filterText: ""
    signal activated(var item)

    readonly property var items: {
        const q = (filterText || "").trim().toLowerCase();
        const out = [];
        const slashes = [
            { kind: "slash", id: "/new", title: "/new", subtitle: qsTr("Start a fresh chat") },
            { kind: "slash", id: "/model", title: "/model", subtitle: qsTr("Switch model") },
            { kind: "slash", id: "/help", title: "/help", subtitle: qsTr("Show commands") }
        ];
        for (let i = 0; i < slashes.length; i++) {
            if (!q || slashes[i].title.indexOf(q) !== -1 || slashes[i].subtitle.toLowerCase().indexOf(q) !== -1)
                out.push(slashes[i]);
        }
        const cmds = Config.ai.commands || [];
        for (let i = 0; i < cmds.length; i++) {
            const c = cmds[i] || {};
            const title = c.name || c.id || qsTr("Command");
            if (!q || title.toLowerCase().indexOf(q) !== -1 || String(c.prompt || "").toLowerCase().indexOf(q) !== -1) {
                out.push({
                    kind: "command",
                    id: c.id || title,
                    title: title,
                    subtitle: qsTr("Saved command"),
                    prompt: c.prompt || "",
                    icon: c.icon || Icons.sparkle
                });
            }
        }
        const history = Ai.chatHistory || [];
        for (let i = 0; i < Math.min(history.length, 6); i++) {
            const h = history[i] || {};
            const title = h.title || qsTr("Chat");
            if (!q || title.toLowerCase().indexOf(q) !== -1) {
                out.push({
                    kind: "chat",
                    id: h.id,
                    title: title,
                    subtitle: qsTr("Recent chat"),
                    icon: Icons.note
                });
            }
        }
        return out;
    }

    implicitHeight: Math.min((items.length * 42) + 16, 320)
    visible: items.length > 0

    layer.enabled: true
    layer.effect: Shadow {}

    ListView {
        id: list
        anchors.fill: parent
        anchors.margins: 8
        clip: true
        spacing: 2
        model: root.items
        boundsBehavior: Flickable.StopAtBounds

        delegate: Item {
            id: row
            required property var modelData
            required property int index
            width: list.width
            height: 40

            StyledRect {
                anchors.fill: parent
                variant: "transparent"
                radius: Styling.popupRadius() - 8
            }

            Rectangle {
                anchors.fill: parent
                radius: Styling.popupRadius() - 8
                color: rowArea.containsMouse ? Styling.tint(Colors.overSurface, Styling.hoverAlpha) : "transparent"
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10

                Text {
                    text: row.modelData.icon || (row.modelData.kind === "slash" ? Icons.sparkle : Icons.note)
                    font.family: Icons.font
                    font.pixelSize: Styling.fontSize(2)
                    color: Styling.srItem("overprimary")
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        text: row.modelData.title
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-1)
                        color: Colors.overSurface
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        text: row.modelData.subtitle || ""
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-4)
                        color: Colors.outline
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
            }

            MouseArea {
                id: rowArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.activated(row.modelData)
            }
        }
    }
}
