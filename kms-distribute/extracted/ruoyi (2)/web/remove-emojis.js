#!/usr/bin/env node
/**
 * Remove all emoji symbols from frontend code
 * Supports: .vue, .js, .ts, .jsx, .tsx, .json files
 */

const fs = require('fs');
const path = require('path');

class EmojiRemover {
    constructor() {
        // Comprehensive emoji regex patterns
        this.emojiPatterns = [
            /[\u{1F300}-\u{1F9FF}]/gu,  // Misc symbols and pictographs
            /[\u{1F600}-\u{1F64F}]/gu,  // Emoticons
            /[\u{1F680}-\u{1F6FF}]/gu,  // Transport and map symbols
            /[\u{2600}-\u{26FF}]/gu,    // Misc symbols
            /[\u{2700}-\u{27BF}]/gu,    // Dingbats
            /[✅❌⚠️🔧📊⏱️💡🎉🗑️🔍📋🎯🚀⭐🔥💻📝🌟🎨🔒🔓📈📉💾💿🖥️⌨️🖱️🖨️📱📲☎️📞📟📠]/g,
        ];
    }

    removeEmojisFromFile(filePath) {
        try {
            let content = fs.readFileSync(filePath, 'utf8');
            const originalLength = content.length;

            // Apply all emoji removal patterns
            for (const pattern of this.emojiPatterns) {
                content = content.replace(pattern, '');
            }

            if (content.length !== originalLength) {
                fs.writeFileSync(filePath, content, 'utf8');
                return originalLength - content.length;
            }
            return 0;
        } catch (e) {
            console.error(`Error processing ${filePath}: ${e.message}`);
            return 0;
        }
    }

    processDirectory(dir) {
        const extensions = ['.vue', '.js', '.ts', '.jsx', '.tsx', '.json'];
        let totalRemoved = 0;

        const processFile = (filePath) => {
            if (extensions.includes(path.extname(filePath))) {
                const removed = this.removeEmojisFromFile(filePath);
                if (removed > 0) {
                    console.log(`  Cleaned: ${filePath} (-${removed} chars)`);
                    totalRemoved += removed;
                }
            }
        };

        const walkDir = (currentPath) => {
            const items = fs.readdirSync(currentPath);
            
            for (const item of items) {
                const fullPath = path.join(currentPath, item);
                const stat = fs.statSync(fullPath);

                if (stat.isDirectory()) {
                    // Skip node_modules and build directories
                    if (!['node_modules', '.git', 'dist', 'build'].includes(item)) {
                        walkDir(fullPath);
                    }
                } else {
                    processFile(fullPath);
                }
            }
        };

        walkDir(dir);
        return totalRemoved;
    }
}

async function main() {
    console.log('='.repeat(70));
    console.log('Starting Frontend Emoji Removal');
    console.log('='.repeat(70));

    const remover = new EmojiRemover();
    
    // Process web directory
    const webDir = path.join(__dirname, '../web');
    if (fs.existsSync(webDir)) {
        console.log(`\nProcessing directory: ${webDir}`);
        const removed = remover.processDirectory(webDir);
        console.log(`Total emoji removed from web: ${removed} characters\n`);
    }

    console.log('='.repeat(70));
    console.log('Emoji removal completed successfully!');
    console.log('='.repeat(70));
}

main().catch(e => {
    console.error('Error:', e);
    process.exit(1);
});

