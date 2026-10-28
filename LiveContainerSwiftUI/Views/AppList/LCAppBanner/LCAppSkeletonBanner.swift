//
//  LCAppSkeletonBanner.swift
//  LiveContainerSwiftUI
//

import SwiftUI

struct LCAppSkeletonBanner: View {
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 5) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.gray.opacity(0.3))
                    .frame(width: 100, height: 16)
                
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.gray.opacity(0.3))
                    .frame(width: 150, height: 12)
                
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.gray.opacity(0.3))
                    .frame(width: 120, height: 8)
            }
            
            Spacer()
            
            RoundedRectangle(cornerRadius: 16)
                .fill(Color(red: 44/255, green: 44/255, blue: 46/255))
                .frame(width: 70, height: 32)
        }
        .padding(.horizontal, 14)
        .padding(.vertical)
        .frame(height: 88)
        .background(RoundedRectangle(cornerRadius: 22).fill(Color(red: 20/255, green: 20/255, blue: 21/255)))
    }
    
}
