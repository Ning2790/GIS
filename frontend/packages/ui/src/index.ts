/** 共享 UI 组件出口 + 设计基线（C · 现代极简）。
 *
 * 引入 '@qh/ui' 即自动加载 tokens.css（设计变量 + 全局基线）。
 * 新增组件后在此导出，供各应用按需引入。
 */
import './tokens.css';

export { default as PageTitle } from './PageTitle.vue';
export { default as QhButton } from './QhButton.vue';
export { default as QhCard } from './QhCard.vue';
export { default as QhEmpty } from './QhEmpty.vue';
export { default as QhInput } from './QhInput.vue';
export { default as QhPagination } from './QhPagination.vue';
export { default as QhTag } from './QhTag.vue';
