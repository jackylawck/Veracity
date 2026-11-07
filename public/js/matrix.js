cat << 'EOF' > public/js/matrix.js
/**
 * =====================================================================
 *  THE VERACITY // EPISTEMOLOGICAL CONSOLE EPILOGUE (STRICT INTEGRITY)
 *  認識論邊界與存證分級聲明（事件驅動解耦 / 零二次 Fetch / 100% 客觀透明）
 * =====================================================================
 */
(function () {
    'use strict';

    var MONO = '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace';

    var S = {
        title: 'background: #000000; color: #00FF41; font-family: ' + MONO + '; font-size: 12px; font-weight: 900; padding: 6px 10px; border-left: 4px solid #00FF41; display: block;',
        body: 'background: #050B05; color: #73F992; font-family: ' + MONO + '; font-size: 11px; line-height: 1.7; padding: 10px 12px; border-left: 4px solid #008F11; display: block; white-space: pre-wrap;',
        red: 'background: #FF003C; color: #FFFFFF; font-family: ' + MONO + '; font-size: 11px; font-weight: bold; padding: 2px 6px; border-radius: 2px;',
        blue: 'background: #00E5FF; color: #000000; font-family: ' + MONO + '; font-size: 11px; font-weight: bold; padding: 2px 6px; border-radius: 2px;',
        cmd: 'background: #003B00; color: #00FF41; font-family: ' + MONO + '; font-size: 10.5px; padding: 3px 8px; border: 1px solid #00FF41; display: block;',
        cmdKey: 'background: #00FF41; color: #000000; font-weight: 900; font-family: ' + MONO + '; padding: 1px 6px; border-radius: 2px;',
        cmdDesc: 'color: #D1D5DB; font-family: ' + MONO + '; padding-left: 8px;'
    };

    function computeTally(records, health, sourceTag) {
        var lastRun = (health && health.last_successful_run_utc) || 'UNAVAILABLE';

        if (!records || !Array.isArray(records) || records.length === 0) {
            return {
                total: 0,
                metadata_only: 0,
                binary_indexed_unverified: 0,
                binary_verified: 0,
                unknown_level: 0,
                lastAuditUtc: lastRun,
                source: sourceTag,
                statusNote: 'UNINITIALIZED: 總帳未就緒或記錄為空 (0 records)'
            };
        }

        var meta = 0;
        var indexed = 0;
        var verified = 0;
        var unknown = 0;

        for (var i = 0; i < records.length; i++) {
            var lvl = records[i].verification_level || 'metadata_only';
            if (lvl === 'binary_verified_local_sha256' || lvl === 'binary_verified_sigstore') {
                verified++;
            } else if (lvl === 'binary_indexed_unverified') {
                indexed++;
            } else if (lvl === 'metadata_only') {
                meta++;
            } else {
                unknown++;
            }
        }

        return {
            total: records.length,
            metadata_only: meta,
            binary_indexed_unverified: indexed,
            binary_verified: verified,
            unknown_level: unknown,
            lastAuditUtc: lastRun,
            source: sourceTag,
            statusNote: '動態載入就緒 (' + records.length + ' dossiers active)'
        };
    }

    async function resolveLedgerStats() {
        if (window.__VERACITY_RECORDS__ && Array.isArray(window.__VERACITY_RECORDS__) && window.__VERACITY_RECORDS__.length > 0) {
            return computeTally(window.__VERACITY_RECORDS__, window.__VERACITY_HEALTH__, 'Memory Hook (window.__VERACITY_RECORDS__)');
        }

        try {
            var responses = await Promise.all([
                fetch('api/records-latest.json').catch(function () { return null; }),
                fetch('api/health.json').catch(function () { return null; })
            ]);

            var recRes = responses[0];
            var heaRes = responses[1];
            var records = [];
            var health = null;

            if (recRes && recRes.ok) {
                var recData = await recRes.json();
                records = recData.records || [];
                window.__VERACITY_RECORDS__ = records;
            }
            if (heaRes && heaRes.ok) {
                health = await heaRes.json();
                window.__VERACITY_HEALTH__ = health;
            }

            return computeTally(records, health, records.length > 0 ? 'Autonomous Fetch (Fallback)' : 'Empty Ledger Payload');
        } catch (e) {
            return computeTally([], null, 'FETCH_FAILED: ' + e.message);
        }
    }

    async function printDeclaration() {
        var stats = await resolveLedgerStats();
        var distributionText = stats.total === 0
            ? 'UNINITIALIZED — 總帳尚未就緒或為空殼 (0 筆)，無法提供統計。'
            : '總計 ' + stats.total + ' 筆 [metadata_only: ' + stats.metadata_only +
              ' | indexed: ' + stats.binary_indexed_unverified +
              ' | binary_verified: ' + stats.binary_verified +
              (stats.unknown_level > 0 ? ' | unknown: ' + stats.unknown_level : '') + ']';

        console.log('%c[ THE VERACITY // EPISTEMOLOGICAL BOUNDARY & BITSTREAM FIXITY ]', S.title);
        console.log(
            '%c' +
            '【認識論邊界聲明 / Epistemological Boundary】\n' +
            '• 官方包裝與歷史敘事是由文字、權力與立場編織的矩陣（The Matrix）。\n' +
            '• 《揭古》不背書公文內容之真偽，亦不做意識形態或歷史裁判。\n' +
            '• 本系統唯一交付的，是總帳級 JSON 的透明簽署（Sigstore/Rekor）與目錄元數據存證。\n' +
            '• 當前存證分佈：' + distributionText + '\n' +
            '• 最近審計時間：' + stats.lastAuditUtc + '\n' +
            '• 二進位原始檔案 SHA-256 哈希鏈屬 Phase 2 目標，當前原卷 fixity 誠實標記為 NONE。\n' +
            '• 歷史的實質解釋權，永遠屬於清醒獨立的公民與學者。',
            S.body
        );
        console.log('%c請輸入 veracity.help() 查看互動指令集', S.cmd);
    }

    var api = Object.freeze({
        help: function () {
            console.log('%c[ VERACITY EPISTEMIC CLI // 指令集 ]', S.title);
            console.log('%cveracity.redPill()%c  - 檢視底層技術邊界：直面誠實的元數據與未完成的哈希鏈', S.cmdKey, S.cmdDesc);
            console.log('%cveracity.bluePill()%c - 檢視敘事優先框架：探討主權公文與歷史定論之平行邊界', S.cmdKey, S.cmdDesc);
            console.log('%cveracity.status()%c   - 非同步檢索總帳動態分級存證指標 (Verification Levels)', S.cmdKey, S.cmdDesc);
            console.log('%cveracity.charter()%c  - 重新輸出完整認識論憲章與當前分級指標', S.cmdKey, S.cmdDesc);
            console.log('%cveracity.manifesto()%c- veracity.charter() 之別名', S.cmdKey, S.cmdDesc);
            return 'Ready for input / 請輸入上述指令執行。';
        },

        redPill: async function () {
            var stats = await resolveLedgerStats();
            console.log('%c[ SELECTION: RED PILL / 選擇：紅藥丸 ]', S.red);
            console.log(
                '%c[技術邊界與位元客觀性]\n' +
                '• 兌現承諾：你面對的是各國檔案館法定解密目錄的檔號、全宗與覆蓋日期。\n' +
                '• 存證現狀：總帳 JSON 經 Sigstore/Rekor 進行 Keyless 簽署以保證管線傳輸未篡改。\n' +
                '  原始掃描原卷之二進位雜湊鏈（Phase 2 目標）當前誠實標記為 NONE。\n' +
                '• 當前分級：總計 ' + stats.total + ' 筆，其中 metadata_only 共 ' + stats.metadata_only +
                ' 筆，binary_verified 共 ' + stats.binary_verified + ' 筆' +
                (stats.unknown_level > 0 ? '，unknown 共 ' + stats.unknown_level + ' 筆。\n' : '。\n') +
                '• 結論：系統不提供現成真相，請透過各案卷 Source Manifest 自行查證實體檔案。',
                'color: #FF5555; font-family: ' + MONO + '; line-height: 1.6;'
            );
            return 'Epistemic honesty acknowledged. Invariant Layer 1 displayed.';
        },

        bluePill: function () {
            console.log('%c[ SELECTION: BLUE PILL / 選擇：藍藥丸 ]', S.blue);
            console.log(
                '%c[敘事優先 / Narrative Framework]\n' +
                '• 視角選擇：你選擇以各主權機構歷史定論、解密新聞稿與主流外交敘事作為理解框架。\n' +
                '• 中立界定：本系統不裁決此選擇之正誤。位元完整性（Layer 1）與歷史實質解釋（Layer 4）為平行維度。\n' +
                '• 責任歸屬：敘事框架之選用不影響 Layer 1 目錄的客觀物理記錄，亦不免除詮釋者之獨立舉證責任。',
                'color: #00E5FF; font-family: ' + MONO + '; line-height: 1.6;'
            );
            return 'Narrative framework retained. Layer 1 constraints remain invariant.';
        },

        status: async function () {
            var stats = await resolveLedgerStats();
            var rows = [
                { '存證等級 (Level)': 'metadata_only', '案卷數量 (Dossiers)': stats.metadata_only, '狀態 (Status)': 'Active (Phase 1 Baseline)' },
                { '存證等級 (Level)': 'binary_indexed_unverified', '案卷數量 (Dossiers)': stats.binary_indexed_unverified, '狀態 (Status)': 'Indexed (Pending Binary Check)' },
                { '存證等級 (Level)': 'binary_verified (local_sha256 | sigstore)', '案卷數量 (Dossiers)': stats.binary_verified, '狀態 (Status)': 'Targeted (Phase 2 Local/Sigstore)' }
            ];
            if (stats.unknown_level > 0) {
                rows.push({ '存證等級 (Level)': 'unknown_unclassified', '案卷數量 (Dossiers)': stats.unknown_level, '狀態 (Status)': 'Warning: Unrecognized Schema Level' });
            }
            console.table(rows);
            console.log(
                '%c總帳狀態: ' + stats.statusNote + ' | 數據源: ' + stats.source + ' | 審計時間: ' + stats.lastAuditUtc,
                'color: #00FF41; font-family: ' + MONO + '; font-size: 10.5px;'
            );
            return 'Ledger fixity distribution displayed.';
        },

        charter: async function () {
            await printDeclaration();
            return 'Epistemological charter printed.';
        },

        manifesto: async function () {
            await printDeclaration();
            return 'Epistemological charter printed.';
        }
    });

    window.veracity = api;
    window.__VERACITY__ = api;

    // 事件驅動與生命週期同步
    var bootExecuted = false;
    function triggerBoot() {
        if (bootExecuted) return;
        bootExecuted = true;
        printDeclaration().catch(function (e) {
            console.warn('[Veracity] Epistemic console initialization notice:', e);
        });
    }

    if (window.__VERACITY_RECORDS__ && Array.isArray(window.__VERACITY_RECORDS__) && window.__VERACITY_RECORDS__.length > 0) {
        triggerBoot();
    } else {
        window.addEventListener('veracity:ready', triggerBoot, { once: true });
        // 3 秒超時兜底（避免獨立測試或網路失敗時靜默無回應）
        setTimeout(triggerBoot, 3000);
    }
})();
EOF
