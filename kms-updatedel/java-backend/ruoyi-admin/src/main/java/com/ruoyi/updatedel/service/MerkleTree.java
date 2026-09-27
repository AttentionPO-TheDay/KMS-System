package com.ruoyi.updatedel.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 二叉 Merkle 树：为批次内每条操作记录生成可独立验证的成员证明。
 *
 * <h2>为什么需要它</h2>
 * 早前的「树型证明」实际上是「把所有 consistencyHash 用 | 拼接后再取一次 SHA-256」，
 * 即一条线性哈希链，只能证明「服务端声称这些记录都在」，
 * <b>无法</b>证明「某一条记录属于该批次」。字段名却用了
 * tree_path / tree_fanout / node_index / verify_message="tree proof verified"，
 * 会让人误以为是 Merkle 证明。
 *
 * <h2>现在的语义</h2>
 * <ul>
 *   <li>叶子：{@code H(0x00 || leafValue)}（域分隔前缀，避免叶子哈希被当作内部节点哈希）</li>
 *   <li>内部节点：{@code H(0x01 || left || right)}</li>
 *   <li>奇数个节点时最后一个直接上提（不复制，避免 CVE-2012-2459 式的可延展性）</li>
 *   <li>证明路径：从叶子到根，记录每一层的兄弟哈希与方向</li>
 * </ul>
 * 验证方可仅凭「叶子值 + 证明路径 + 根」独立重算，不需要访问数据库。
 */
public final class MerkleTree {

    private static final byte LEAF_PREFIX = 0x00;
    private static final byte NODE_PREFIX = 0x01;

    private final List<String> leaves;
    /** 每层节点哈希：levels.get(0) 为叶子层，最后一层为 [root]。 */
    private final List<List<String>> levels;

    public MerkleTree(List<String> leafValues) {
        if (leafValues == null || leafValues.isEmpty()) {
            throw new IllegalArgumentException("Merkle 树至少需要一个叶子");
        }
        // 复制并过滤空值，保证叶子顺序与调用方提供的顺序一致
        List<String> normalized = new ArrayList<>(leafValues.size());
        for (String value : leafValues) {
            normalized.add(value == null ? "" : value);
        }
        this.leaves = Collections.unmodifiableList(normalized);
        this.levels = buildLevels(normalized);
    }

    /** 返回 Merkle 根（十六进制小写）。 */
    public String getRoot() {
        List<String> top = levels.get(levels.size() - 1);
        return top.get(0);
    }

    /** 叶子数量。 */
    public int size() {
        return leaves.size();
    }

    /**
     * 生成指定叶子的证明路径。
     *
     * @param leafIndex 叶子下标（0 基）
     * @return 每层一个条目，形如 {@code "L:<siblingHash>"} 或 {@code "R:<siblingHash>"}
     *         （L 表示兄弟在左、R 表示兄弟在右）；最后以 {@code "ROOT:<hash>"} 结尾
     */
    public List<String> getProof(int leafIndex) {
        if (leafIndex < 0 || leafIndex >= leaves.size()) {
            throw new IllegalArgumentException("叶子下标越界: " + leafIndex);
        }
        List<String> proof = new ArrayList<>();
        int index = leafIndex;
        // 最后一层只有一个节点（根），不参与兄弟比较
        for (int level = 0; level < levels.size() - 1; level++) {
            List<String> current = levels.get(level);
            int siblingIndex = (index % 2 == 0) ? index + 1 : index - 1;
            if (siblingIndex < current.size()) {
                String side = (index % 2 == 0) ? "R" : "L";
                proof.add(side + ":" + current.get(siblingIndex));
            }
            // 没有兄弟时（奇数上提）该层不产生证明条目
            index = index / 2;
        }
        proof.add("ROOT:" + getRoot());
        return proof;
    }

    /**
     * 独立验证：仅用叶子值、证明路径与预期根即可重算，不依赖树对象。
     *
     * @param leafValue 叶子原始值
     * @param proof     由 {@link #getProof(int)} 生成的路径
     * @param expectedRoot 预期根
     * @return 是否通过
     */
    public static boolean verify(String leafValue, List<String> proof, String expectedRoot) {
        if (leafValue == null || proof == null || proof.isEmpty() || expectedRoot == null) {
            return false;
        }
        String computed = hashLeaf(leafValue);
        String rootInProof = null;
        for (String entry : proof) {
            if (entry == null || entry.length() < 3) {
                return false;
            }
            int sep = entry.indexOf(':');
            if (sep <= 0) {
                return false;
            }
            String side = entry.substring(0, sep);
            String value = entry.substring(sep + 1);
            if ("ROOT".equals(side)) {
                rootInProof = value;
                continue;
            }
            if ("L".equals(side)) {
                computed = hashNode(value, computed);
            } else if ("R".equals(side)) {
                computed = hashNode(computed, value);
            } else {
                return false;
            }
        }
        if (rootInProof != null && !rootInProof.equalsIgnoreCase(expectedRoot)) {
            return false;
        }
        return computed.equalsIgnoreCase(expectedRoot);
    }

    // ------------------------------------------------------------------
    // 内部实现
    // ------------------------------------------------------------------

    private static List<List<String>> buildLevels(List<String> leafValues) {
        List<List<String>> allLevels = new ArrayList<>();
        List<String> current = new ArrayList<>(leafValues.size());
        for (String value : leafValues) {
            current.add(hashLeaf(value));
        }
        allLevels.add(Collections.unmodifiableList(current));

        while (current.size() > 1) {
            List<String> next = new ArrayList<>((current.size() + 1) / 2);
            for (int i = 0; i < current.size(); i += 2) {
                if (i + 1 < current.size()) {
                    next.add(hashNode(current.get(i), current.get(i + 1)));
                } else {
                    // 奇数个：最后一个直接上提
                    next.add(current.get(i));
                }
            }
            current = next;
            allLevels.add(Collections.unmodifiableList(current));
        }
        return Collections.unmodifiableList(allLevels);
    }

    /**
     * 计算叶子哈希：{@code H(0x00 || value)}。
     * <p>
     * 公开以便独立验证方在服务端之外复现同一算法。
     */
    public static String hashLeaf(String value) {
        return sha256Hex(LEAF_PREFIX, value.getBytes(StandardCharsets.UTF_8));
    }

    /**
     * 计算内部节点哈希：{@code H(0x01 || left || right)}。
     * <p>
     * 公开以便独立验证方在服务端之外复现同一算法。
     */
    public static String hashNode(String left, String right) {
        byte[] l = left.getBytes(StandardCharsets.UTF_8);
        byte[] r = right.getBytes(StandardCharsets.UTF_8);
        byte[] combined = new byte[1 + l.length + r.length];
        combined[0] = NODE_PREFIX;
        System.arraycopy(l, 0, combined, 1, l.length);
        System.arraycopy(r, 0, combined, 1 + l.length, r.length);
        return sha256Hex(combined);
    }

    private static String sha256Hex(byte prefix, byte[] payload) {
        byte[] input = new byte[1 + payload.length];
        input[0] = prefix;
        System.arraycopy(payload, 0, input, 1, payload.length);
        return sha256Hex(input);
    }

    private static String sha256Hex(byte[] input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] out = digest.digest(input);
            StringBuilder builder = new StringBuilder(out.length * 2);
            for (byte b : out) {
                builder.append(String.format("%02x", b));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 不可用", ex);
        }
    }
}