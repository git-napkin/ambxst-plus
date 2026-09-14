import QtQuick
import qs.modules.theme
import qs.modules.components
import qs.config

StyledRect {
    id: root
    property string latex: ""
    property string content: ""

    variant: "internalbg"
    radius: Styling.radius(-4)
    implicitHeight: mathText.contentHeight + 20
    clip: true

    TextEdit {
        id: mathText
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        textFormat: TextEdit.PlainText
        horizontalAlignment: Text.AlignHCenter
        height: contentHeight
        text: root.content || root.latex
        color: Colors.overSurface
        font.family: Config.theme.monoFont
        font.pixelSize: Styling.monoFontSize(0)
    }
}
