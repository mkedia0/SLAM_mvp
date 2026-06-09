import SwiftUI

struct WarehouseMapPreview: View {
    let samples: [ARFrameSample]
    let labels: [WarehouseLabel]

    var body: some View {
        Canvas { context, size in
            drawGrid(context: context, size: size)
            let points = samples.map { $0.pose }
            let bounds = boundsFor(points: points + labels.map(\.position))
            let projectedPoints = points.map { project($0, in: bounds, size: size) }
            if projectedPoints.count > 1 {
                var path = Path()
                path.move(to: projectedPoints[0])
                for point in projectedPoints.dropFirst() {
                    path.addLine(to: point)
                }
                context.stroke(path, with: .color(.cyan), lineWidth: 3)
            }
            for point in projectedPoints.suffix(240) {
                context.fill(Path(ellipseIn: CGRect(x: point.x - 2, y: point.y - 2, width: 4, height: 4)), with: .color(.white.opacity(0.75)))
            }
            for label in labels.prefix(24) {
                let point = project(label.position, in: bounds, size: size)
                context.fill(Path(ellipseIn: CGRect(x: point.x - 6, y: point.y - 6, width: 12, height: 12)), with: .color(label.color))
                let text = Text(label.title).font(.caption2).foregroundStyle(.white)
                context.draw(text, at: CGPoint(x: point.x + 42, y: point.y - 14), anchor: .center)
            }
        }
        .frame(minHeight: 280)
        .background(.black.opacity(0.9), in: RoundedRectangle(cornerRadius: 8))
        .overlay(alignment: .topLeading) {
            Text("Top-down XYZ map")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.8))
                .padding(10)
        }
    }

    private func drawGrid(context: GraphicsContext, size: CGSize) {
        var grid = Path()
        for x in stride(from: 0, through: size.width, by: 42) {
            grid.move(to: CGPoint(x: x, y: 0))
            grid.addLine(to: CGPoint(x: x, y: size.height))
        }
        for y in stride(from: 0, through: size.height, by: 42) {
            grid.move(to: CGPoint(x: 0, y: y))
            grid.addLine(to: CGPoint(x: size.width, y: y))
        }
        context.stroke(grid, with: .color(.white.opacity(0.08)), lineWidth: 1)
    }

    private func boundsFor(points: [Vector3]) -> (minX: Double, maxX: Double, minZ: Double, maxZ: Double) {
        guard !points.isEmpty else { return (-1, 1, -1, 1) }
        let xs = points.map(\.x)
        let zs = points.map(\.z)
        return (xs.min() ?? -1, xs.max() ?? 1, zs.min() ?? -1, zs.max() ?? 1)
    }

    private func project(_ point: Vector3, in bounds: (minX: Double, maxX: Double, minZ: Double, maxZ: Double), size: CGSize) -> CGPoint {
        let pad = 28.0
        let spanX = max(0.5, bounds.maxX - bounds.minX)
        let spanZ = max(0.5, bounds.maxZ - bounds.minZ)
        let x = pad + ((point.x - bounds.minX) / spanX) * (size.width - pad * 2)
        let y = size.height - pad - ((point.z - bounds.minZ) / spanZ) * (size.height - pad * 2)
        return CGPoint(x: x, y: y)
    }
}
