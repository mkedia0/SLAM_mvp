import SwiftUI

@main
struct MNetMapperApp: App {
    @StateObject private var store = MappingStore()

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environmentObject(store)
        }
    }
}
