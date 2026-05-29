import SwiftUI

struct RootTabView: View {
    var body: some View {
        TabView {
            MappingView()
                .tabItem {
                    Label("Mapping", systemImage: "map")
                }

            TrainingView()
                .tabItem {
                    Label("Training", systemImage: "camera.macro")
                }

            ProcessingView()
                .tabItem {
                    Label("Processing", systemImage: "cpu")
                }

            ResultsView()
                .tabItem {
                    Label("Results", systemImage: "tablecells")
                }
        }
    }
}
