import QtQuick
import QtQuick.Effects
import QtQuick.Shapes
import Quickshell
import Quickshell.Wayland
import qs.modules.components
import qs.modules.corners
import qs.modules.services
import qs.modules.theme
import qs.config

Item {
    id: root

    required property ShellScreen targetScreen
    property bool hasFullscreenWindow: false

    // State source: Singletons and Registry
    readonly property bool userFrameEnabled: Config.bar?.frameEnabled ?? false
    readonly property bool computerUseActive: ComputerUse.sessionActive
    property real cuOpacity: computerUseActive ? 1 : 0
    readonly property bool frameEnabled: userFrameEnabled || computerUseActive || cuOpacity > 0.01
    readonly property bool configContainBar: Config.bar?.containBar ?? false
    readonly property string barPos: Config.bar?.position ?? "top"
    readonly property string notchPos: Config.notchPosition ?? "top"
    
    readonly property var barPanel: Visibilities.barPanels[targetScreen.name]
    readonly property var dockPanel: Visibilities.dockPanels[targetScreen.name]
    
    // Effective Reveal States
    readonly property bool barReveal: barPanel ? barPanel.reveal : true
    readonly property bool dockReveal: dockPanel ? dockPanel.reveal : true
    readonly property bool notchReveal: barPanel ? barPanel.notchReveal : true

    // Hover States for Restoration Logic
    readonly property bool barHovered: barPanel ? (barPanel.barHoverActive || barPanel.notchHoverActive || barPanel.notchOpen) : false
    readonly property bool dockHovered: dockPanel ? (dockPanel.reveal && (dockPanel.activeWindowFullscreen || dockPanel.keepHidden || !dockPanel.pinned)) : false
    readonly property real baseThickness: {
        const base = Config.bar?.frameThickness ?? 6;
        const clamped = Math.max(0, Math.min(Math.round(base), 40));
        if (root.computerUseActive)
            return Math.max(clamped, 4);
        return clamped;
    }

    readonly property int barSize: {
        if (!barPanel) return 44;
        const isHoriz = barPos === "top" || barPos === "bottom";
        return isHoriz ? barPanel.barTargetHeight : barPanel.barTargetWidth;
    }

    // --- Animation Synchronization ---
    
    property real _barAnimProgress: barReveal ? 1.0 : 0.0
    Behavior on _barAnimProgress {
        enabled: Config.animDuration > 0
        NumberAnimation { duration: Config.animDuration / 2; easing.type: Easing.OutCubic }
    }

    property real _dockAnimProgress: dockReveal ? 1.0 : 0.0
    Behavior on _dockAnimProgress {
        enabled: Config.animDuration > 0
        NumberAnimation { duration: Config.animDuration / 2; easing.type: Easing.OutCubic }
    }

    property real _notchAnimProgress: notchReveal ? 1.0 : 0.0
    Behavior on _notchAnimProgress {
        enabled: Config.animDuration > 0
        NumberAnimation { duration: Config.animDuration / 2; easing.type: Easing.OutCubic }
    }

    Behavior on cuOpacity {
        enabled: Config.animDuration > 0
        NumberAnimation {
            duration: Config.animDuration
            easing.type: Styling.animEasing
        }
    }

    // Bar expansion logic (synchronized with bar reveal)
    // Only expand if the user's frame is enabled and bar is being contained.
    // Computer-use must not steal exclusive zone / jump containBar layout.
    readonly property int barExpansion: (userFrameEnabled && configContainBar) ? Math.round((barSize + baseThickness) * _barAnimProgress) : 0

    // --- Side-Specific Thickness Restoration ---

    readonly property int topThickness: calculateSideThickness("top")
    readonly property int bottomThickness: calculateSideThickness("bottom")
    readonly property int leftThickness: calculateSideThickness("left")
    readonly property int rightThickness: calculateSideThickness("right")

    function calculateSideThickness(side) {
        let t = baseThickness;
        if (hasFullscreenWindow && !root.computerUseActive) {
            let restore = false;
            let progress = 0.0;

            if (barPos === side && barHovered) { restore = true; progress = Math.max(progress, _barAnimProgress); }
            if (notchPos === side && barHovered) { restore = true; progress = Math.max(progress, _notchAnimProgress); }
            if (dockPanel && dockPanel.position === side && dockHovered) { restore = true; progress = Math.max(progress, _dockAnimProgress); }
            
            t = restore ? (baseThickness * progress) : 0;
        }
        
        let expansion = (userFrameEnabled && configContainBar && barPos === side) ? barExpansion : 0;
        return Math.round(t) + expansion;
    }

    // --- Corner Logic ---
    
    readonly property real targetInnerRadius: {
        if (root.computerUseActive) return Styling.radius(4);
        if (!root.hasFullscreenWindow) return Styling.radius(4);
        if (!barHovered && !dockHovered) return 0;
        
        let progress = Math.max(_barAnimProgress, _dockAnimProgress, _notchAnimProgress);
        return Styling.radius(4) * progress;
    }
    
    property real innerRadius: targetInnerRadius

    readonly property color cuColor1: {
        const p = Colors.computerUseFramePalette;
        return (p && p.length) ? p[0] : Colors.primary;
    }
    readonly property color cuColor2: {
        const p = Colors.computerUseFramePalette;
        return (p && p.length > 1) ? p[1] : Colors.tertiary;
    }
    readonly property color cuColor3: {
        const p = Colors.computerUseFramePalette;
        return (p && p.length > 2) ? p[2] : Colors.secondary;
    }

    property real cuSweepAngle: 0
    NumberAnimation on cuSweepAngle {
        running: root.computerUseActive || root.cuOpacity > 0.01
        from: 0
        to: 360
        duration: 7000
        loops: Animation.Infinite
    }

    property real cuGlow: 0.55
    SequentialAnimation on cuGlow {
        running: root.computerUseActive || root.cuOpacity > 0.01
        loops: Animation.Infinite
        NumberAnimation {
            to: 1.0
            duration: 1100
            easing.type: Easing.InOutSine
        }
        NumberAnimation {
            to: 0.55
            duration: 1100
            easing.type: Easing.InOutSine
        }
    }

    // --- Visuals ---

    StyledRect {
        id: frameFill
        anchors.fill: parent
        variant: "bg"
        radius: 0
        enableBorder: false
        visible: root.frameEnabled
        layer.enabled: root.frameEnabled
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: frameMask
            maskInverted: true
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }
    }

    Item {
        id: cuFrameFill
        anchors.fill: parent
        visible: root.cuOpacity > 0.01
        opacity: root.cuOpacity * (0.34 + 0.26 * root.cuGlow)
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: frameMask
            maskInverted: true
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer

            ShapePath {
                strokeWidth: 0
                strokeColor: "transparent"
                fillGradient: ConicalGradient {
                    centerX: cuFrameFill.width / 2
                    centerY: cuFrameFill.height / 2
                    angle: root.cuSweepAngle
                    GradientStop {
                        position: 0.0
                        color: root.cuColor1
                    }
                    GradientStop {
                        position: 0.33
                        color: root.cuColor2
                    }
                    GradientStop {
                        position: 0.66
                        color: root.cuColor3
                    }
                    GradientStop {
                        position: 1.0
                        color: root.cuColor1
                    }
                }
                PathMove {
                    x: 0
                    y: 0
                }
                PathLine {
                    x: cuFrameFill.width
                    y: 0
                }
                PathLine {
                    x: cuFrameFill.width
                    y: cuFrameFill.height
                }
                PathLine {
                    x: 0
                    y: cuFrameFill.height
                }
                PathLine {
                    x: 0
                    y: 0
                }
            }
        }
    }

    Item {
        id: frameMask
        anchors.fill: parent
        visible: false
        layer.enabled: true

        Rectangle {
            id: maskRect
            x: root.leftThickness
            y: root.topThickness
            width: parent.width - (root.leftThickness + root.rightThickness)
            height: parent.height - (root.topThickness + root.bottomThickness)
            radius: root.innerRadius
            color: "white"
            visible: width > 0 && height > 0
        }
    }
}
