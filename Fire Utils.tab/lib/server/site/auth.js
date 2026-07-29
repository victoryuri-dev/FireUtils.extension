'use strict';
var Auth = {
  _key: 'fu_session',
  getUser: function () {
    try { return JSON.parse(sessionStorage.getItem(this._key)); }
    catch (e) { return null; }
  },
  setUser: function (u) { sessionStorage.setItem(this._key, JSON.stringify(u)); },
  logout:  function () { sessionStorage.removeItem(this._key); window.location.href = '/login'; },
  require: function () {
    var u = this.getUser();
    if (!u) { window.location.href = '/login'; return null; }
    return u;
  },
};
