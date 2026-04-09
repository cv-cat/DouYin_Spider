ea = function() {
    return (ea = Object.assign || function(e) {
        for (var t, n = 1, r = arguments.length; n < r; n++)
            for (var o in t = arguments[n])
                Object.prototype.hasOwnProperty.call(t, o) && (e[o] = t[o]);
        return e
    }
    ).apply(this, arguments)
}
var H = function(e) {
    for (var t, n = e.toString(), r = [], o = 0; o < n.length; o++)
        0 <= (t = n.charCodeAt(o)) && t <= 127 ? r.push(t) : 128 <= t && t <= 2047 ? (r.push(192 | 31 & t >> 6),
        r.push(128 | 63 & t)) : (2048 <= t && t <= 55295 || 57344 <= t && t <= 65535) && (r.push(224 | 15 & t >> 12),
        r.push(128 | 63 & t >> 6),
        r.push(128 | 63 & t));
    for (var i = 0; i < r.length; i++)
        r[i] &= 255;
    return r
}
V = function(e) {
    var t = []
      , n = [];
    if (void 0 === e)
        return "";
    n = H(e);
    for (var r = 0, o = n.length; r < o; ++r)
        t.push((5 ^ n[r]).toString(16));
    return t.join("")
}
function generate_account_sdk_source_info(){
    let browserInfo = {
        "hardwareConcurrency": 20,
        "webdriver": false,
        "chromedriver": false,
        "shelldriver": false,
        "plugins": 5,
        "permissions": [
            {
                "name": "notifications",
                "state": "prompt"
            }
        ],
        "innerHeight": 1442,
        "innerWidth": 1166,
        "outerHeight": 1552,
        "outerWidth": 2560,
        "stoargeStatus": {
            "indexedDB": {
                "idb": "object",
                "open": "function",
                "indexedDB": "object",
                "IDBKeyRange": "function",
                "openDatabase": "undefined",
                "isSafari": false,
                "hasFetch": false
            },
            "localStorage": {
                "isSupportLStorage": true,
                "size": 46382,
                "write": true
            },
            "storageQuotaStatus": {
                "usage": 149822,
                "quota": 128849645568,
                "isPrivate": false
            }
        },
        "notificationPermission": "default",
        "performance": {
            // "timeOrigin": 1723036093298,
            "timeOrigin": new Date().getTime(),
            "usedJSHeapSize": 137509473,
            "navigationTiming": {
                "decodedBodySize": 633258,
                "entryType": "navigation",
                "initiatorType": "navigation",
                "name": "https://www.douyin.com/?recommend=1",
                "renderBlockingStatus": "non-blocking",
                "serverTiming": "inner,tt_agw,cdn-cache,edge,origin",
                "guleStart": 1496.2999999523163,
                "guleDuration": 14.799999952316284
            }
        }
    }
    let data = {
        request_host: "www.douyin.com",
        request_pathname: '/'
    }
    return V(JSON.stringify(ea(ea({}, browserInfo || {}), data)))
}
// console.log(generate_account_sdk_source_info())


eD = function(e, t) {
    var n, r = 0, o = 0;
    if ("object" != typeof e || !t || t.length <= 0)
        return e;
    for (var i = ej({
        mix_mode: r
    }, e), a = 0, c = t.length; a < c; ++a)
        void 0 !== (n = i[t[a]]) && (r |= 1,
        o |= 1,
        i[t[a]] = eN(n));
    return i.mix_mode = r,
    i.fixed_mix_mode = o,
    i
}
var ek = function(e) {
    for (var t, n = e.toString(), r = [], o = 0; o < n.length; o++)
        0 <= (t = n.charCodeAt(o)) && t <= 127 ? r.push(t) : 128 <= t && t <= 2047 ? (r.push(192 | 31 & t >> 6),
        r.push(128 | 63 & t)) : (2048 <= t && t <= 55295 || 57344 <= t && t <= 65535) && (r.push(224 | 15 & t >> 12),
        r.push(128 | 63 & t >> 6),
        r.push(128 | 63 & t));
    for (var i = 0; i < r.length; i++)
        r[i] &= 255;
    return r
}
eN = function(e) {
    var t = []
      , n = [];
    if (void 0 === e)
        return "";
    n = ek(e);
    for (var r = 0, o = n.length; r < o; ++r)
        t.push((5 ^ n[r]).toString(16));
    return t.join("")
}
ej = function() {
    return (ej = Object.assign || function(e) {
        for (var t, n = 1, r = arguments.length; n < r; n++)
            for (var o in t = arguments[n])
                Object.prototype.hasOwnProperty.call(t, o) && (e[o] = t[o]);
        return e
    }
    ).apply(this, arguments)
};
function generateSecretPhoneNum(phoneNum) {
    return eD({
        "mobile": "+86 " + phoneNum,
        "type": 24,
        "is6Digits": 1
    }, ["mobile", "type"])
}
// let res = eD({
//     "mobile": "+86 15751076989",
//     "type": 24,
//     "is6Digits": 1
// }, ["mobile", "type"])
//
// console.log(res)
nx = function() {
    return (nx = Object.assign || function(e) {
        for (var t, n = 1, r = arguments.length; n < r; n++)
            for (var o in t = arguments[n])
                Object.prototype.hasOwnProperty.call(t, o) && (e[o] = t[o]);
        return e
    }
    ).apply(this, arguments)
}
function generateSecretCode(phoneNum, code) {
    return eD({
        "mobile": "+86 " + phoneNum,
        "code": code,
        "service": "https://www.douyin.com"
    }, ["mobile", "code", "password"])
}
// console.log(generateSecretCode("15751076989", "090625"))