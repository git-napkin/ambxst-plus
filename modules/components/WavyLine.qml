import QtQuick
import QtQuick.Window
import qs.config
import qs.modules.theme

Canvas {
    id: root

    renderStrategy: Canvas.Threaded
    renderTarget: Canvas.Image

    // =========================================================================
    // API Properties
    // =========================================================================
    property color color: Styling.srItem("overprimary")
    property real lineWidth: 2
    property real frequency: 2
    property real amplitudeMultiplier: 0.5
    property real fullLength: width
    property bool running: true

    // Legacy compatibility
    property real amplitude: lineWidth * amplitudeMultiplier
    property real speed: 5  // Not used with Date.now() technique, kept for API compat
    property bool animationsEnabled: true

    // =========================================================================
    // Rendering
    // =========================================================================
    readonly property bool shouldAnimate: running && animationsEnabled &&
                                          visible && width > 0 && opacity > 0 &&
                                          (!Window.window || Window.window.visible) &&
                                          (!Config.performance || Config.performance.wavyLine)

    onPaint: {
        var ctx = getContext("2d");
        ctx.clearRect(0, 0, width, height);

        if (!root.shouldAnimate || width <= 0 || height <= 0) return;

        var amp = root.lineWidth * root.amplitudeMultiplier;
        var freq = root.frequency;
        var phase = Date.now() / 400.0;
        var centerY = height / 2;
        var step = Math.max(2, Math.ceil(root.lineWidth));
        var xStart = ctx.lineWidth / 2;
        var xEnd = root.width - ctx.lineWidth / 2;

        ctx.strokeStyle = root.color;
        ctx.lineWidth = root.lineWidth;
        ctx.lineCap = "round";
        ctx.beginPath();

        for (var x = xStart; x <= xEnd; x += step) {
            var waveY = centerY + amp * Math.sin(freq * 2 * Math.PI * x / root.fullLength + phase);
            if (x === xStart)
                ctx.moveTo(x, waveY);
            else
                ctx.lineTo(x, waveY);
        }
        if (xEnd > xStart) {
            var endY = centerY + amp * Math.sin(freq * 2 * Math.PI * xEnd / root.fullLength + phase);
            ctx.lineTo(xEnd, endY);
        }

        ctx.stroke();
    }

    onShouldAnimateChanged: requestPaint()
    onWidthChanged: if (shouldAnimate) requestPaint()
    onHeightChanged: if (shouldAnimate) requestPaint()

    // ~30 FPS is enough for a sine overlay; a display-synced paint of every
    // pixel across the width was wasting GPU time while idle-looking UI sat on screen.
    Timer {
        interval: 32
        running: root.shouldAnimate
        repeat: true
        onTriggered: root.requestPaint()
    }
}
