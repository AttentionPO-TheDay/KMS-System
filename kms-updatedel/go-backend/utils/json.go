package utils

import (
	"github.com/bytedance/sonic"
)

// SonicMarshal is a fast JSON encoder using Sonic.
var SonicMarshal = sonic.Marshal

// SonicUnmarshal is a fast JSON decoder using Sonic.
var SonicUnmarshal = sonic.Unmarshal
