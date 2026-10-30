<script setup lang="ts">
import { computed } from 'vue';

/** full：AI 页整身展示；peek：地图页头探头挥手。 */
const props = withDefaults(
  defineProps<{
    variant?: 'full' | 'peek';
    action?: 'idle' | 'scratch' | 'laugh' | 'fall' | 'wave' | 'spin' | 'sneeze' | 'dance' | 'jump' | 'angry' | 'startle';
  }>(),
  { variant: 'full', action: 'idle' },
);
const viewBox = computed(() => (props.variant === 'peek' ? '0 0 240 205' : '0 0 240 232'));
</script>

<template>
  <svg
    class="ai-mascot"
    :class="[`ai-mascot--${variant}`, `ai-mascot--${action}`]"
    :viewBox="viewBox"
    role="img"
    aria-label="天境源康 AI 助手雪山云灵"
    xmlns="http://www.w3.org/2000/svg"
  >
    <!-- 整体纵向压缩，形成矮胖的 Q 版比例 -->
    <g transform="scale(1 0.85)">
      <!-- 冰蓝光环与雪花 -->
      <g>
        <circle cx="120" cy="104" r="94" fill="#93c5fd" opacity="0.1" />
        <circle cx="120" cy="104" r="86" fill="#bfdbfe" opacity="0.06" />
        <circle
          cx="120"
          cy="104"
          r="84"
          fill="none"
          stroke="#93c5fd"
          stroke-opacity="0.34"
          stroke-width="1"
          stroke-dasharray="2 9"
        />
        <path
          d="M120 12v6M120 190v6M28 104h6M206 104h6"
          stroke="#93c5fd"
          stroke-opacity="0.55"
          stroke-width="1.2"
          stroke-linecap="round"
        />
        <g stroke="#bfdbfe" stroke-width="1.4" stroke-linecap="round" opacity="0.9">
          <path d="M186 52v12M180 58h12M181 53l10 10M191 53l-10 10" />
          <path d="M44 76v9M39.5 80.5h9M41 77.5l7 7M48 77.5l-7 7" opacity="0.75" />
        </g>
        <circle cx="196" cy="150" r="2" fill="#bfdbfe" />
        <circle cx="48" cy="142" r="1.4" fill="#bfdbfe" opacity="0.7" />
      </g>

      <!-- 站立阴影 -->
      <ellipse cx="120" cy="266" rx="42" ry="7" fill="#93c5fd" opacity="0.24" />

      <!-- 短粗小短腿与雪地靴 -->
      <path d="M99 216H113V238C113 241 110 243 106 243C102 243 99 241 99 238Z" fill="#1e3a5f" />
      <path
        d="M127 216H141V238C141 241 138 243 134 243C130 243 127 241 127 238Z"
        fill="#1e3a5f"
      />
      <path
        d="M89 240C89 236 92 233 97 233H114C118 233 120 236 120 240V250C120 256 116 260 109 260C101 260 89 256 89 250Z"
        fill="#162c49"
      />
      <path
        d="M121 240C121 236 124 233 129 233H146C150 233 152 236 152 240V250C152 256 148 260 141 260C134 260 121 256 121 250Z"
        fill="#162c49"
      />
      <path
        d="M92 250C99 255 111 256 119 251"
        fill="none"
        stroke="#2b4d78"
        stroke-width="2.5"
        stroke-linecap="round"
      />
      <path
        d="M124 250C130 255 141 256 149 251"
        fill="none"
        stroke="#2b4d78"
        stroke-width="2.5"
        stroke-linecap="round"
      />
      <path
        d="M89 254C97 258 112 258 120 252"
        fill="none"
        stroke="#a5d8f7"
        stroke-width="2"
        stroke-linecap="round"
        opacity="0.55"
      />
      <path
        d="M121 254C129 258 143 258 152 252"
        fill="none"
        stroke="#a5d8f7"
        stroke-width="2"
        stroke-linecap="round"
        opacity="0.55"
      />

      <!-- 圆圆的小外套 -->
      <path
        d="M90 142C80 155 74 174 74 194C74 208 81 218 93 222H147C159 218 166 208 166 194C166 174 160 155 150 142Z"
        fill="#1e3a5f"
      />
      <path
        d="M74 194C74 208 81 218 93 222H147C159 218 166 208 166 194C154 209 138 215 120 215C102 215 86 209 74 194Z"
        fill="#162c49"
        opacity="0.65"
      />
      <path
        d="M120 162V221"
        stroke="#a5d8f7"
        stroke-width="1.3"
        stroke-linecap="round"
        opacity="0.35"
      />

      <g
        class="ai-mascot__head"
        :transform="variant === 'peek' ? 'rotate(-8 120 132)' : undefined"
      >
      <!-- 云朵脑袋 -->
      <path
        d="M120 38C106 38 94 45 88 56C74 54 62 64 62 80C62 95 73 106 88 106C91 120 104 131 120 131C136 131 149 120 152 106C167 106 178 95 178 80C178 64 166 54 152 56C146 45 134 38 120 38Z"
        fill="#f8fcff"
        stroke="#c7dcf0"
        stroke-width="2.5"
      />
      <path
        d="M88 56C94 45 106 38 120 38C134 38 146 45 152 56C140 50 100 50 88 56Z"
        fill="#e3f0fc"
      />
      <path
        d="M88 106C91 120 104 131 120 131C136 131 149 120 152 106C143 114 97 114 88 106Z"
        fill="#e3f0fc"
        opacity="0.8"
      />
      <path
        d="M68 86C72 79 78 75 85 76"
        fill="none"
        stroke="#dbeafe"
        stroke-width="2"
        stroke-linecap="round"
      />

      <!-- 毛线帽 -->
      <circle cx="120" cy="18" r="9" fill="#f8fcff" stroke="#c7dcf0" stroke-width="2.5" />
      <path
        d="M107 15C111 11 116 10 120 12"
        fill="none"
        stroke="#ffffff"
        stroke-width="2"
        stroke-linecap="round"
      />
      <path
        d="M86 62C86 40 101 27 120 27C139 27 154 40 154 62Z"
        fill="#1e3a5f"
      />
      <path
        d="M81 54C81 48 85 44 91 44H149C155 44 159 48 159 54V65C159 71 155 75 149 75H91C85 75 81 71 81 65Z"
        fill="#2b4d78"
      />
      <path
        d="M84 62H156"
        stroke="#a5d8f7"
        stroke-width="2"
        stroke-linecap="round"
        opacity="0.5"
      />
      <path
        d="M88 50V68M96 48V70M104 47V71M136 47V71M144 48V70M152 50V68"
        stroke="#3f6f9c"
        stroke-width="1.2"
        stroke-linecap="round"
        opacity="0.55"
      />
      <path
        d="M92 58l1.3 3.4 3.4 1.3-3.4 1.3-1.3 3.4-1.3-3.4-3.4-1.3 3.4-1.3z"
        fill="#a5d8f7"
      />

      <!-- 腮红 -->
      <ellipse
        cx="84"
        cy="109"
        rx="9"
        ry="4"
        fill="#f2b8b0"
        opacity="0.42"
      />
      <ellipse
        cx="156"
        cy="111"
        rx="9"
        ry="4"
        fill="#f2b8b0"
        opacity="0.42"
      />

      <!-- 表情随互动变化 -->
      <g v-if="action === 'laugh' || action === 'jump'">
        <path
          d="M91 96C95 90 104 90 108 96"
          fill="none"
          stroke="#17233b"
          stroke-width="2.8"
          stroke-linecap="round"
        />
        <path
          d="M132 96C136 90 145 90 149 96"
          fill="none"
          stroke="#17233b"
          stroke-width="2.8"
          stroke-linecap="round"
        />
        <path
          d="M109 108C112 120 128 120 131 108C124 113 116 113 109 108Z"
          fill="#17233b"
        />
        <ellipse cx="120" cy="116" rx="4" ry="2" fill="#f2a7a0" />
      </g>
      <g v-else-if="action === 'fall'">
        <path
          d="M94 90l8 8M102 90l-8 8"
          fill="none"
          stroke="#17233b"
          stroke-width="2.6"
          stroke-linecap="round"
        />
        <path
          d="M134 93l8 8M142 93l-8 8"
          fill="none"
          stroke="#17233b"
          stroke-width="2.6"
          stroke-linecap="round"
        />
        <ellipse cx="120" cy="113" rx="4.5" ry="5.5" fill="#17233b" />
        <ellipse cx="120" cy="115" rx="2.2" ry="1.2" fill="#f2a7a0" />
      </g>
      <g v-else-if="action === 'angry'">
        <path
          d="M91 87L108 91"
          fill="none"
          stroke="#17233b"
          stroke-width="2.4"
          stroke-linecap="round"
        />
        <path
          d="M132 91L149 87"
          fill="none"
          stroke="#17233b"
          stroke-width="2.4"
          stroke-linecap="round"
        />
        <ellipse cx="99" cy="97" rx="5.8" ry="8" fill="#17233b" />
        <ellipse cx="141" cy="99" rx="6.2" ry="8.6" fill="#17233b" />
        <circle cx="97" cy="94" r="1.8" fill="#ffffff" />
        <circle cx="139" cy="96" r="2" fill="#ffffff" />
        <path
          d="M114 115C117 110 123 110 126 115"
          fill="none"
          stroke="#17233b"
          stroke-width="2.2"
          stroke-linecap="round"
        />
      </g>
      <g v-else-if="action === 'startle'">
        <ellipse
          cx="99"
          cy="92"
          rx="8.5"
          ry="10.5"
          fill="#fbf4ee"
          stroke="#17233b"
          stroke-width="2"
        />
        <ellipse
          cx="141"
          cy="95"
          rx="9"
          ry="11"
          fill="#fbf4ee"
          stroke="#17233b"
          stroke-width="2"
        />
        <circle cx="99" cy="93" r="3.2" fill="#17233b" />
        <circle cx="141" cy="96" r="3.4" fill="#17233b" />
        <circle cx="97" cy="89.5" r="1.5" fill="#ffffff" />
        <circle cx="139" cy="92.5" r="1.6" fill="#ffffff" />
        <ellipse cx="120" cy="114" rx="4.5" ry="6" fill="#17233b" />
      </g>
      <g v-else-if="action === 'sneeze'">
        <path
          d="M92 96C96 91 104 91 108 96"
          fill="none"
          stroke="#17233b"
          stroke-width="2.8"
          stroke-linecap="round"
        />
        <path
          d="M132 96C136 91 144 91 148 96"
          fill="none"
          stroke="#17233b"
          stroke-width="2.8"
          stroke-linecap="round"
        />
        <ellipse cx="120" cy="113" rx="3.6" ry="4.2" fill="#17233b" />
      </g>
      <g v-else>
        <g class="ai-mascot__eye-look">
          <g class="ai-mascot__eyes">
            <ellipse cx="99" cy="94" rx="6.2" ry="9" fill="#17233b" />
          <ellipse cx="141" cy="97" rx="6.8" ry="9.8" fill="#17233b" />
          <circle cx="97" cy="90.5" r="2.2" fill="#ffffff" />
          <circle cx="139" cy="93" r="2.4" fill="#ffffff" />
          <circle cx="101" cy="98" r="1.1" fill="#a5e3f0" />
            <circle cx="143" cy="101" r="1.2" fill="#a5e3f0" />
          </g>
        </g>
        <path
          d="M112 112C113 119 127 119 128 112C124 115 116 115 112 112Z"
          fill="#17233b"
        />
        <ellipse cx="120" cy="117" rx="3.2" ry="1.7" fill="#f2a7a0" />
      </g>

      <!-- 耳侧终端 -->
      <circle cx="178" cy="98" r="9" fill="#1e3a5f" stroke="#162c49" stroke-width="1.5" />
      <circle cx="178" cy="98" r="3.2" fill="#a5e3f0" />
      <path
        d="M174 92C178 90 183 91.5 184.5 95.5"
        fill="none"
        stroke="#a5d8f7"
        stroke-width="1.4"
        stroke-linecap="round"
        opacity="0.65"
      />

      </g>

      <!-- 围巾与胸章 -->
      <path
        d="M86 128C100 142 140 142 154 128L158 150C141 162 99 162 82 150Z"
        fill="#c7d2fe"
      />
      <path
        d="M145 145C156 148 165 157 169 170L158 175C154 163 149 156 141 153Z"
        fill="#a5b4fc"
      />
      <path
        d="M88 137C96 145 108 149 120 149"
        fill="none"
        stroke="#818cf8"
        stroke-width="1.5"
        stroke-linecap="round"
        opacity="0.7"
      />

      <!-- 小手臂与手套 -->
      <g class="ai-mascot__arm--left">
        <path
          d="M79 172C69 178 65 190 70 199C76 199 84 192 89 184"
          fill="#2b4d78"
          stroke="#162c49"
          stroke-width="1.4"
          stroke-linejoin="round"
        />
        <circle cx="69" cy="199" r="7" fill="#35608f" />
      </g>
      <g
        v-if="
          variant !== 'peek' && action !== 'scratch' && action !== 'wave' && action !== 'dance'
        "
        class="ai-mascot__arm--right"
      >
        <path
          d="M161 172C171 178 175 190 170 199C164 199 156 192 151 184"
          fill="#2b4d78"
          stroke="#162c49"
          stroke-width="1.4"
          stroke-linejoin="round"
        />
        <circle cx="171" cy="199" r="7" fill="#35608f" />
      </g>
      <g
        v-if="variant === 'peek' || action === 'scratch' || action === 'wave' || action === 'dance'"
        class="ai-mascot__arm--wave"
      >
        <path
          d="M154 168C157 154 166 138 178 126C182 121 188 122 191 127C184 140 174 156 166 176Z"
          fill="#2b4d78"
          stroke="#162c49"
          stroke-width="1.4"
          stroke-linejoin="round"
        />
        <circle cx="188" cy="123" r="7.5" fill="#35608f" />
        <circle cx="185" cy="120" r="2" fill="#5c88b5" />
      </g>

      <circle cx="120" cy="190" r="11" fill="#f8fcff" stroke="#a5d8f7" stroke-width="2" />
      <path d="M112 194L117 184L120 190L124 182L129 194Z" fill="#2b4d78" />
      <circle cx="120" cy="190" r="14" fill="none" stroke="#a5d8f7" opacity="0.4" />
    </g>
  </svg>
</template>

<style scoped>
.ai-mascot {
  display: block;
  width: 100%;
  height: auto;
}
.ai-mascot--full.ai-mascot--idle {
  animation: ai-mascot-idle 7.5s ease-in-out infinite;
  transform-origin: 50% 100%;
}
.ai-mascot--full.ai-mascot--idle .ai-mascot__head {
  transform-box: fill-box;
  transform-origin: 50% 92%;
  animation: ai-mascot-head-idle 8.8s ease-in-out infinite;
}
.ai-mascot--idle .ai-mascot__eyes {
  transform-box: fill-box;
  transform-origin: 50% 50%;
  animation: ai-mascot-blink 5.6s ease-in-out infinite;
}
.ai-mascot--full.ai-mascot--idle .ai-mascot__eye-look {
  transform-box: fill-box;
  transform-origin: 50% 50%;
  animation: ai-mascot-idle-eye-look 9s ease-in-out infinite;
}
.ai-mascot--full.ai-mascot--idle .ai-mascot__arm--left {
  transform-box: fill-box;
  transform-origin: 55% 5%;
  animation: ai-mascot-idle-arm-left 7.5s ease-in-out infinite;
}
.ai-mascot--full.ai-mascot--idle .ai-mascot__arm--right {
  transform-box: fill-box;
  transform-origin: 45% 5%;
  animation: ai-mascot-idle-arm-right 7.5s ease-in-out infinite;
}
.ai-mascot--laugh {
  animation: ai-mascot-laugh 2s cubic-bezier(0.36, 0.07, 0.19, 0.97);
  transform-origin: 50% 100%;
}
.ai-mascot--fall {
  animation: ai-mascot-fall 2.8s cubic-bezier(0.37, 0, 0.22, 1);
  transform-origin: 50% 50%;
}
.ai-mascot--fall .ai-mascot__head {
  transform-box: fill-box;
  transform-origin: 50% 92%;
  animation: ai-mascot-fall-head 2.8s cubic-bezier(0.37, 0, 0.22, 1);
}
.ai-mascot--fall .ai-mascot__arm--left {
  transform-box: fill-box;
  transform-origin: 55% 5%;
  animation: ai-mascot-fall-arm-left 2.8s cubic-bezier(0.37, 0, 0.22, 1);
}
.ai-mascot--fall .ai-mascot__arm--right {
  transform-box: fill-box;
  transform-origin: 45% 5%;
  animation: ai-mascot-fall-arm-right 2.8s cubic-bezier(0.37, 0, 0.22, 1);
}
.ai-mascot--wave {
  animation: ai-mascot-wave-body 1.8s ease-in-out;
  transform-origin: 50% 100%;
}
.ai-mascot--spin {
  animation: ai-mascot-spin 2.2s cubic-bezier(0.4, 0, 0.2, 1);
  transform-origin: 50% 60%;
}
.ai-mascot--sneeze {
  animation: ai-mascot-sneeze-body 1.8s ease-in-out;
  transform-origin: 50% 100%;
}
.ai-mascot--sneeze .ai-mascot__head {
  transform-box: fill-box;
  transform-origin: 50% 92%;
  animation: ai-mascot-sneeze-head 1.8s ease-in-out;
}
.ai-mascot--dance {
  animation: ai-mascot-dance-body 2s ease-in-out;
  transform-origin: 50% 100%;
}
.ai-mascot--dance .ai-mascot__head {
  transform-box: fill-box;
  transform-origin: 50% 92%;
  animation: ai-mascot-dance-head 2s ease-in-out;
}
.ai-mascot--dance .ai-mascot__arm--wave {
  transform-box: fill-box;
  transform-origin: 8% 92%;
  animation: ai-mascot-dance-arm 0.55s ease-in-out infinite;
}
.ai-mascot--jump {
  animation: ai-mascot-jump 2.1s cubic-bezier(0.3, 0.7, 0.4, 1);
  transform-origin: 50% 100%;
}
.ai-mascot--jump .ai-mascot__head {
  transform-box: fill-box;
  transform-origin: 50% 92%;
  animation: ai-mascot-jump-head 2.1s cubic-bezier(0.3, 0.7, 0.4, 1);
}
.ai-mascot--jump .ai-mascot__arm--left {
  transform-box: fill-box;
  transform-origin: 55% 5%;
  animation: ai-mascot-jump-arm-left 2.1s ease-in-out;
}
.ai-mascot--jump .ai-mascot__arm--right {
  transform-box: fill-box;
  transform-origin: 45% 5%;
  animation: ai-mascot-jump-arm-right 2.1s ease-in-out;
}
.ai-mascot--angry {
  animation: ai-mascot-angry-body 1.9s ease-in-out;
  transform-origin: 50% 100%;
}
.ai-mascot--angry .ai-mascot__head {
  transform-box: fill-box;
  transform-origin: 50% 92%;
  animation: ai-mascot-angry-head 1.9s ease-in-out;
}
.ai-mascot--startle {
  animation: ai-mascot-startle-body 1.8s cubic-bezier(0.2, 0.8, 0.3, 1);
  transform-origin: 50% 100%;
}
.ai-mascot--startle .ai-mascot__head {
  transform-box: fill-box;
  transform-origin: 50% 92%;
  animation: ai-mascot-startle-head 1.8s cubic-bezier(0.2, 0.8, 0.3, 1);
}
.ai-mascot--startle .ai-mascot__arm--left {
  transform-box: fill-box;
  transform-origin: 55% 5%;
  animation: ai-mascot-startle-arm-left 1.8s ease-in-out;
}
.ai-mascot--startle .ai-mascot__arm--right {
  transform-box: fill-box;
  transform-origin: 45% 5%;
  animation: ai-mascot-startle-arm-right 1.8s ease-in-out;
}
.ai-mascot--scratch {
  animation: ai-mascot-scratch-body 1.7s ease-in-out;
  transform-origin: 50% 100%;
}
.ai-mascot--scratch .ai-mascot__head {
  transform-box: fill-box;
  transform-origin: 50% 92%;
  animation: ai-mascot-scratch-head 1.7s cubic-bezier(0.37, 0, 0.63, 1);
}
.ai-mascot--scratch .ai-mascot__arm--wave {
  transform-box: fill-box;
  transform-origin: 8% 92%;
  animation: ai-mascot-scratch-arm 0.5s ease-in-out infinite;
}
.ai-mascot--wave .ai-mascot__arm--wave {
  transform-box: fill-box;
  transform-origin: 8% 92%;
  animation: ai-mascot-wave-hand 0.7s ease-in-out infinite;
}
.ai-mascot--peek .ai-mascot__arm--wave {
  transform-box: fill-box;
  transform-origin: 8% 92%;
  animation: ai-mascot-wave 2.4s ease-in-out infinite;
}
@keyframes ai-mascot-idle {
  0%,
  100% {
    transform: translate(0, 0) rotate(0deg);
  }
  22% {
    transform: translate(-1px, -6px) rotate(1deg);
  }
  44% {
    transform: translate(0, 0) rotate(0deg);
  }
  60% {
    transform: translate(1px, -2px) rotate(-1deg);
  }
  74% {
    transform: translate(0, -10px) rotate(0.5deg);
  }
  84% {
    transform: translate(0, 0) rotate(0deg);
  }
}
@keyframes ai-mascot-head-idle {
  0%,
  100% {
    transform: rotate(0deg);
  }
  20% {
    transform: rotate(-4deg);
  }
  45% {
    transform: rotate(-2deg);
  }
  68% {
    transform: rotate(4deg);
  }
  86% {
    transform: rotate(2deg);
  }
}
@keyframes ai-mascot-idle-eye-look {
  0%,
  100% {
    transform: translateX(0);
  }
  25%,
  45% {
    transform: translateX(-3px);
  }
  65%,
  85% {
    transform: translateX(3px);
  }
}
@keyframes ai-mascot-idle-arm-left {
  0%,
  100% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(8deg);
  }
}
@keyframes ai-mascot-idle-arm-right {
  0%,
  100% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(-8deg);
  }
}
@keyframes ai-mascot-blink {
  0%,
  90%,
  96%,
  100% {
    transform: scaleY(1);
  }
  93% {
    transform: scaleY(0.12);
  }
}
@keyframes ai-mascot-laugh {
  0%,
  100% {
    transform: translateY(0) rotate(0deg) scale(1);
  }
  10% {
    transform: translateY(-9px) rotate(-4deg) scale(1.04, 0.96);
  }
  22% {
    transform: translateY(0) rotate(4deg) scale(0.96, 1.04);
  }
  34% {
    transform: translateY(-12px) rotate(-4deg) scale(1.04, 0.96);
  }
  46% {
    transform: translateY(0) rotate(4deg) scale(0.96, 1.04);
  }
  58% {
    transform: translateY(-10px) rotate(-3deg) scale(1.02, 0.98);
  }
  72% {
    transform: translateY(0) rotate(1deg) scale(1);
  }
}
@keyframes ai-mascot-fall {
  0% {
    transform: translate(0, 0) rotate(0deg) scale(1);
    animation-timing-function: ease-out;
  }
  6% {
    transform: translate(0, -2px) rotate(-2deg) scale(1.01, 0.99);
  }
  14% {
    transform: translate(-1px, -4px) rotate(-5deg) scale(0.99, 1.01);
    animation-timing-function: cubic-bezier(0.5, 0.05, 0.9, 0.45);
  }
  26% {
    transform: translate(0, 2px) rotate(8deg) scale(1);
  }
  38% {
    transform: translate(4px, 10px) rotate(30deg) scale(0.97);
  }
  48% {
    transform: translate(7px, 12px) rotate(62deg) scale(0.88);
    animation-timing-function: cubic-bezier(0.16, 0.84, 0.22, 1.08);
  }
  54% {
    transform: translate(9px, 14px) rotate(72deg) scale(0.82, 0.8);
  }
  60% {
    transform: translate(8px, 12px) rotate(70deg) scale(0.84, 0.82);
    animation-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
  }
  68% {
    transform: translate(5px, 8px) rotate(58deg) scale(0.88);
  }
  78% {
    transform: translate(3px, 2px) rotate(32deg) scale(0.94);
  }
  88% {
    transform: translate(-1px, -3px) rotate(-5deg) scale(1.01, 0.99);
    animation-timing-function: ease-in-out;
  }
  95% {
    transform: translate(0, 0) rotate(1.5deg) scale(1);
  }
  100% {
    transform: translate(0, 0) rotate(0deg) scale(1);
  }
}
@keyframes ai-mascot-fall-head {
  0%,
  14% {
    transform: rotate(0deg);
  }
  26% {
    transform: rotate(-1deg);
  }
  38% {
    transform: rotate(-4deg);
  }
  48% {
    transform: rotate(-6deg);
  }
  54% {
    transform: rotate(3deg);
  }
  60% {
    transform: rotate(4deg);
  }
  68% {
    transform: rotate(2deg);
  }
  78% {
    transform: rotate(-1deg);
  }
  88% {
    transform: rotate(1deg);
  }
  100% {
    transform: rotate(0deg);
  }
}
@keyframes ai-mascot-fall-arm-left {
  0%,
  14%,
  100% {
    transform: rotate(0deg);
  }
  26% {
    transform: rotate(-4deg);
  }
  38% {
    transform: rotate(6deg);
  }
  48% {
    transform: rotate(10deg);
  }
  60% {
    transform: rotate(8deg);
  }
  78% {
    transform: rotate(2deg);
  }
}
@keyframes ai-mascot-fall-arm-right {
  0%,
  14%,
  100% {
    transform: rotate(0deg);
  }
  26% {
    transform: rotate(4deg);
  }
  38% {
    transform: rotate(-6deg);
  }
  48% {
    transform: rotate(-10deg);
  }
  60% {
    transform: rotate(-8deg);
  }
  78% {
    transform: rotate(-2deg);
  }
}
@keyframes ai-mascot-wave-body {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }
  30% {
    transform: translateY(-5px) rotate(-5deg);
  }
  70% {
    transform: translateY(0) rotate(5deg);
  }
}
@keyframes ai-mascot-wave-hand {
  0%,
  100% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(-38deg);
  }
}
@keyframes ai-mascot-spin {
  0% {
    transform: translateY(0) rotate(0deg) scale(1);
  }
  18% {
    transform: translateY(-12px) rotate(0deg) scale(0.9);
  }
  55% {
    transform: translateY(-15px) rotate(720deg) scale(0.8);
  }
  75% {
    transform: translateY(0) rotate(720deg) scale(0.96);
  }
  100% {
    transform: translateY(0) rotate(720deg) scale(1);
  }
}
@keyframes ai-mascot-sneeze-body {
  0%,
  100% {
    transform: translateY(0) rotate(0deg) scale(1);
  }
  22% {
    transform: translateY(-5px) rotate(-5deg) scale(1.03, 0.97);
  }
  35% {
    transform: translateY(-8px) rotate(-8deg) scale(1.03, 0.97);
  }
  45% {
    transform: translateY(3px) rotate(6deg) scale(0.94, 1.06);
  }
  55% {
    transform: translateY(-1px) rotate(-1deg) scale(1.01, 0.99);
  }
  70% {
    transform: translateY(0) rotate(0deg) scale(1);
  }
}
@keyframes ai-mascot-sneeze-head {
  0%,
  20%,
  100% {
    transform: rotate(0deg);
  }
  35% {
    transform: rotate(-15deg);
  }
  45% {
    transform: rotate(13deg);
  }
  55% {
    transform: rotate(-2deg);
  }
  70% {
    transform: rotate(1deg);
  }
}
@keyframes ai-mascot-dance-body {
  0%,
  100% {
    transform: translateX(0) translateY(0) rotate(0deg);
  }
  15% {
    transform: translateX(-7px) translateY(-5px) rotate(-5deg);
  }
  30% {
    transform: translateX(0) translateY(0) rotate(0deg);
  }
  45% {
    transform: translateX(7px) translateY(-5px) rotate(5deg);
  }
  60% {
    transform: translateX(0) translateY(0) rotate(0deg);
  }
  75% {
    transform: translateX(-5px) translateY(-3px) rotate(-4deg);
  }
  90% {
    transform: translateX(0) translateY(0) rotate(0deg);
  }
}
@keyframes ai-mascot-dance-head {
  0%,
  100% {
    transform: rotate(0deg);
  }
  20% {
    transform: rotate(8deg);
  }
  40% {
    transform: rotate(-8deg);
  }
  60% {
    transform: rotate(8deg);
  }
  80% {
    transform: rotate(-8deg);
  }
}
@keyframes ai-mascot-dance-arm {
  0%,
  100% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(-36deg);
  }
}
@keyframes ai-mascot-jump {
  0%,
  100% {
    transform: translateY(0) scale(1);
  }
  12% {
    transform: translateY(8px) scale(1.06, 0.9);
  }
  28% {
    transform: translateY(-16px) scale(0.95, 1.06);
  }
  42% {
    transform: translateY(-22px) scale(0.97, 1.04);
  }
  56% {
    transform: translateY(-14px) scale(0.98, 1.03);
  }
  70% {
    transform: translateY(8px) scale(1.08, 0.88);
  }
  80% {
    transform: translateY(-12px) scale(0.99, 1.02);
  }
  88% {
    transform: translateY(0) scale(1.02, 0.98);
  }
  94% {
    transform: translateY(-3px) scale(1);
  }
}
@keyframes ai-mascot-jump-head {
  0%,
  100% {
    transform: rotate(0deg);
  }
  28% {
    transform: rotate(-4deg);
  }
  50% {
    transform: rotate(3deg);
  }
  70% {
    transform: rotate(-3deg);
  }
  86% {
    transform: rotate(1deg);
  }
}
@keyframes ai-mascot-jump-arm-left {
  0%,
  100% {
    transform: rotate(0deg);
  }
  30% {
    transform: rotate(45deg);
  }
  52% {
    transform: rotate(55deg);
  }
  70% {
    transform: rotate(-4deg);
  }
}
@keyframes ai-mascot-jump-arm-right {
  0%,
  100% {
    transform: rotate(0deg);
  }
  30% {
    transform: rotate(-45deg);
  }
  52% {
    transform: rotate(-55deg);
  }
  70% {
    transform: rotate(4deg);
  }
}
@keyframes ai-mascot-angry-body {
  0%,
  100% {
    transform: translateX(0) translateY(0) rotate(0deg) scale(1);
  }
  10% {
    transform: translateX(-7px) translateY(0) rotate(-3deg) scale(1);
  }
  20% {
    transform: translateX(7px) translateY(0) rotate(3deg) scale(1);
  }
  30% {
    transform: translateX(-7px) translateY(0) rotate(-3deg) scale(1);
  }
  40% {
    transform: translateX(7px) translateY(0) rotate(3deg) scale(1);
  }
  50% {
    transform: translateX(0) translateY(-5px) rotate(0deg) scale(0.98, 1.02);
  }
  60% {
    transform: translateX(0) translateY(8px) rotate(0deg) scale(1.05, 0.95);
  }
  72% {
    transform: translateX(0) translateY(0) rotate(0deg) scale(1);
  }
  84% {
    transform: translateX(-4px) translateY(0) rotate(-2deg) scale(1);
  }
  92% {
    transform: translateX(4px) translateY(0) rotate(2deg) scale(1);
  }
}
@keyframes ai-mascot-angry-head {
  0%,
  100% {
    transform: rotate(0deg);
  }
  12% {
    transform: rotate(-9deg);
  }
  24% {
    transform: rotate(9deg);
  }
  36% {
    transform: rotate(-10deg);
  }
  48% {
    transform: rotate(10deg);
  }
  62% {
    transform: rotate(-4deg);
  }
  78% {
    transform: rotate(3deg);
  }
}
@keyframes ai-mascot-startle-body {
  0%,
  100% {
    transform: translate(0, 0) rotate(0deg) scale(1);
  }
  14% {
    transform: translate(0, 7px) rotate(0deg) scale(1.04, 0.94);
  }
  34% {
    transform: translate(-6px, -15px) rotate(-4deg) scale(0.95, 1.06);
  }
  50% {
    transform: translate(2px, -13px) rotate(3deg) scale(1);
  }
  68% {
    transform: translate(0, 2px) rotate(0deg) scale(1.03, 0.97);
  }
  82% {
    transform: translate(0, -5px) rotate(-1deg) scale(1);
  }
  92% {
    transform: translate(0, 0) rotate(1deg) scale(1);
  }
}
@keyframes ai-mascot-startle-head {
  0%,
  100% {
    transform: rotate(0deg);
  }
  16% {
    transform: rotate(7deg);
  }
  36% {
    transform: rotate(-10deg);
  }
  55% {
    transform: rotate(4deg);
  }
  74% {
    transform: rotate(-3deg);
  }
  88% {
    transform: rotate(1deg);
  }
}
@keyframes ai-mascot-startle-arm-left {
  0%,
  100% {
    transform: rotate(0deg);
  }
  30% {
    transform: rotate(42deg);
  }
  52% {
    transform: rotate(30deg);
  }
  72% {
    transform: rotate(-4deg);
  }
}
@keyframes ai-mascot-startle-arm-right {
  0%,
  100% {
    transform: rotate(0deg);
  }
  30% {
    transform: rotate(-42deg);
  }
  52% {
    transform: rotate(-30deg);
  }
  72% {
    transform: rotate(4deg);
  }
}
@keyframes ai-mascot-scratch-head {
  0%,
  100% {
    transform: rotate(0deg);
  }
  18% {
    transform: rotate(-10deg);
  }
  36% {
    transform: rotate(8deg);
  }
  54% {
    transform: rotate(-12deg);
  }
  72% {
    transform: rotate(6deg);
  }
}
@keyframes ai-mascot-scratch-arm {
  0%,
  100% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(-28deg);
  }
}
@keyframes ai-mascot-scratch-body {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }
  25% {
    transform: translateY(-3px) rotate(-3deg);
  }
  55% {
    transform: translateY(0) rotate(3deg);
  }
  80% {
    transform: translateY(-2px) rotate(-2deg);
  }
}
@keyframes ai-mascot-wave {
  0%,
  58%,
  100% {
    transform: rotate(0deg);
  }
  68% {
    transform: rotate(-12deg);
  }
  78% {
    transform: rotate(7deg);
  }
  88% {
    transform: rotate(-9deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .ai-mascot--full.ai-mascot--idle,
  .ai-mascot--full.ai-mascot--idle .ai-mascot__head,
  .ai-mascot--full.ai-mascot--idle .ai-mascot__eye-look,
  .ai-mascot--full.ai-mascot--idle .ai-mascot__arm--left,
  .ai-mascot--full.ai-mascot--idle .ai-mascot__arm--right,
  .ai-mascot--idle .ai-mascot__eyes,
  .ai-mascot--laugh,
  .ai-mascot--fall,
  .ai-mascot--fall .ai-mascot__head,
  .ai-mascot--fall .ai-mascot__arm--left,
  .ai-mascot--fall .ai-mascot__arm--right,
  .ai-mascot--wave,
  .ai-mascot--wave .ai-mascot__arm--wave,
  .ai-mascot--spin,
  .ai-mascot--sneeze,
  .ai-mascot--sneeze .ai-mascot__head,
  .ai-mascot--dance,
  .ai-mascot--dance .ai-mascot__head,
  .ai-mascot--dance .ai-mascot__arm--wave,
  .ai-mascot--jump,
  .ai-mascot--jump .ai-mascot__head,
  .ai-mascot--jump .ai-mascot__arm--left,
  .ai-mascot--jump .ai-mascot__arm--right,
  .ai-mascot--angry,
  .ai-mascot--angry .ai-mascot__head,
  .ai-mascot--startle,
  .ai-mascot--startle .ai-mascot__head,
  .ai-mascot--startle .ai-mascot__arm--left,
  .ai-mascot--startle .ai-mascot__arm--right,
  .ai-mascot--scratch,
  .ai-mascot--scratch .ai-mascot__head,
  .ai-mascot--scratch .ai-mascot__arm--wave,
  .ai-mascot--peek .ai-mascot__arm--wave {
    animation: none;
  }
}
</style>
